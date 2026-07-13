// 本地高危词汇拦截（第一道防线）
import { sm3 } from 'sm-crypto';

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

/**
 * 生成双向国密 SM3 签名安全请求头，用于防篡改和防重放
 */
export function generateSignatureHeaders(data?: any): {
  'x-signature': string;
  'x-timestamp': string;
  'x-nonce': string;
} {
  const timestamp = String(Date.now());
  // 生成 32 位随机字符 nonce
  const nonce = (
    Math.random().toString(36).substring(2, 10) +
    Math.random().toString(36).substring(2, 10) +
    Math.random().toString(36).substring(2, 10) +
    Math.random().toString(36).substring(2, 10)
  ).substring(0, 32);

  let bodyStr = '';
  if (data && typeof data === 'object' && Object.keys(data).length > 0) {
    // 保持 stringify 键的顺序与后端一致
    bodyStr = JSON.stringify(data);
  } else if (typeof data === 'string') {
    bodyStr = data;
  }

  const rawData = `${timestamp}${nonce}${bodyStr}`;
  const signature = sm3(rawData);

  return {
    'x-signature': signature,
    'x-timestamp': timestamp,
    'x-nonce': nonce,
  };
}

