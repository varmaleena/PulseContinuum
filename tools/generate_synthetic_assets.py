"""Render clearly labeled synthetic discharge fixtures from the fictional cohort."""
import json
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate():
    assets = Path(__file__).resolve().parents[1] / 'backend' / 'sample_assets'
    dataset = json.loads((assets / 'synthetic_cohort.json').read_text(encoding='utf-8'))
    styles = getSampleStyleSheet()
    body = ParagraphStyle('ClinicalBody', parent=styles['BodyText'], fontSize=9, leading=13, spaceAfter=7)
    mono = ParagraphStyle('MachineRows', parent=body, fontName='Courier', fontSize=7, leading=11)
    heading = ParagraphStyle('ClinicalHeading', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor('#18755d'), spaceBefore=13, spaceAfter=7)
    for record in dataset['episodes']:
        path = assets / f'{record["episode_id"]}-discharge.pdf'
        document = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=42, leftMargin=42, topMargin=38, bottomMargin=38,
                                     title=f'SYNTHETIC discharge fixture - {record["episode_id"]}')
        story = [Paragraph('SYNTHETIC RECORD / HACKATHON DEMONSTRATION', heading),
                 Paragraph('Post-discharge care summary', styles['Title']),
                 Paragraph('Fictional patient, clinician and care plan. This is not a real prescription or treatment recommendation.', body),
                 Spacer(1, 8)]
        rows = [
            ['Patient', f'{record["name"]}, {record["age"]} years, {record["sex"]}'],
            ['Episode', f'{record["patient_id"]} / {record["episode_id"]}'],
            ['Facility', record['facility']], ['Care unit', record['care_unit']],
            ['Admission / discharge', f'{record["admitted_at"]} / {record["discharged_at"]}'],
            ['Care team', record['clinician']], ['Recovery pathway', record['condition']],
            ['Caregiver / language', f'{record["caregiver_relation"]} / {record["preferred_language"]}'],
        ]
        table = Table([[Paragraph(escape(key), body), Paragraph(escape(value), body)] for key, value in rows], colWidths=[125, 386])
        table.setStyle(TableStyle([('VALIGN', (0,0),(-1,-1),'TOP'), ('BACKGROUND',(0,0),(0,-1),colors.HexColor('#f0f6f3')),
                                   ('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#e0e8e3')), ('LEFTPADDING',(0,0),(-1,-1),9),
                                   ('TOPPADDING',(0,0),(-1,-1),5), ('BOTTOMPADDING',(0,0),(-1,-1),3)]))
        story.append(table)
        for title, content in [('History & allergies', record['history'] + record['allergies']),
                               ('Discharge observations', [f'{key}: {value}' for key,value in record['discharge_vitals'].items()]),
                               ('Handoff & follow-up', [record['handoff_note'],record['follow_up']])]:
            story.append(Paragraph(title, heading))
            story.extend(Paragraph(escape(line), body) for line in content)
        story.append(Paragraph('Fictional formulary / parser test rows', heading))
        for medication in record['medications']:
            line = f'MEDICATION|{medication["name"]}|{medication["strength"]}|{medication["schedule"]}'
            story.append(Paragraph(escape(line), mono))
        for flag in record['red_flags']:
            story.append(Paragraph(escape(f'RED_FLAG|{flag}'), mono))
        story.append(Paragraph(f'Dataset: {dataset["dataset_id"]}. Reference date: {dataset["reference_date"]}. All records are synthetic.', body))
        document.build(story)
        print(path.name)


if __name__ == '__main__':
    generate()
