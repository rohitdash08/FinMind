// PATCH: 此為 AI 生成的修復建議，請人工審查後合併
export interface DeduplicationConfig {
  threshold: number;
  fields: string[];
}

const config: DeduplicationConfig = {
  threshold: parseFloat(process.env.DEDUPLICATION_THRESHOLD || '0.9'),
  fields: (process.env.DEDUPLICATION_FIELDS || 'date,amount,description,category').split(','),
};

export default config;
