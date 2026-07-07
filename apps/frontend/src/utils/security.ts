// 本地高危词汇拦截（第一道防线）
export const HIGH_RISK_KEYWORDS = [
  '处方药',
  '偏方',
  '退烧贴',
  '包治百病',
  '神药',
  '祖传',
  '保证治好',
  '断根',
];

export function containsHighRiskWords(text: string): boolean {
  if (!text) return false;
  for (const word of HIGH_RISK_KEYWORDS) {
    if (text.includes(word)) {
      return true;
    }
  }
  return false;
}
