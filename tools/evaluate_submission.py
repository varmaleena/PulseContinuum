"""Offline, deterministic safety regression. No model calls or clinical-outcome claims."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from agentcore.guardrails import verify_medications  # noqa: E402
from agentcore.vision_forensics import ClinicalEvidence  # noqa: E402


def main():
    formulary = [{'name': 'Pantoprazole', 'strength': '40mg'}, {'name': 'Paracetamol', 'strength': '500mg'}]
    cases = []
    for medication in formulary:
        for strength, readable, expected in [(medication['strength'], True, True),
                (medication['strength'], False, False), ('4000mg', True, False), ('', True, False)]:
            evidence = [{**medication, 'strength': strength, 'label_readable': readable}]
            cases.append((f"{medication['name']} / {strength or 'missing'} / readable={readable}", evidence, expected))
    cases.extend([
        ('No image evidence', [], False),
        ('Unknown drug', [{'name': 'Ibuprofen', 'strength': '400mg', 'label_readable': True}], False),
        ('Missing readability', [{'name': 'Pantoprazole', 'strength': '40mg'}], False),
        ('String true must not pass', [{'name': 'Pantoprazole', 'strength': '40mg', 'label_readable': 'true'}], False),
        ('Mixed matched/unmatched labels', [dict(formulary[0], label_readable=True),
            {'name': 'Unknown', 'strength': '40mg', 'label_readable': True}], False),
        ('Case-insensitive exact label', [{'name': 'PANTOPRAZOLE', 'strength': '40MG', 'label_readable': True}], True),
        ('Color is not identity', [{'name': 'blue tablet', 'strength': '40mg', 'label_readable': True}], False),
        ('Both formulary labels readable', [dict(m, label_readable=True) for m in formulary], True),
    ])
    results = []
    start = perf_counter()
    for name, evidence, expected in cases:
        actual = verify_medications(evidence, formulary)['dosage_verified']
        results.append({'case': name, 'expected': expected, 'actual': actual, 'passed': actual == expected})
    for score in [-1, 101, 'invalid']:
        rejected = False
        try:
            ClinicalEvidence.model_validate({'identified_medications': [], 'clinical_red_flags': [],
                'readmission_risk_score': score, 'summary': 'Synthetic evaluation'})
        except ValueError:
            rejected = True
        results.append({'case': f'Invalid model score {score}', 'passed': rejected})
    report = {'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Offline deterministic label/formulary gate and model schema; no clinical efficacy or model accuracy measurement',
        'total': len(results), 'passed': sum(row['passed'] for row in results),
        'elapsed_ms': round((perf_counter() - start) * 1000, 3), 'cases': results}
    target = ROOT / 'submission' / 'evaluation-results.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"{report['passed']}/{report['total']} safety cases passed; {target}")
    return 0 if report['passed'] == report['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
