export type Profile = 'care' | 'admin';
export const profileCookie = 'pulse-profile';
export const adminPage = (path: string) => ['/agentcore', '/telemetry'].some(prefix => path === prefix || path.startsWith(prefix + '/'));
export const careApi = (path: string) => /^\/api\/(health|scenarios|patients(?:\/[^/]+)?|pharmacy|fixtures\/[^/]+\/discharge\.pdf|audits\/[^/]+\.pdf|media\/[^/]+|workflow\/(ingest-discharge|whatsapp-multimodal|simulate-deadzone-failover|caregiver-sms-reply|rcs-action|replay-scenario|clinical-review|acknowledge-plan|follow-up|coordination-event|send-demo-email|reset))$/.test(path);
