/** 测试 DeepSeek 配置连通性 */
import * as dotenv from 'dotenv';
import * as path from 'path';
dotenv.config({ path: path.resolve(__dirname, '..', '.env') });

function resolveConfig(): { apiKey: string; baseUrl: string; model: string } | null {
  const apiKey = (process.env.DEEPSEEK_API_KEY || '').trim();
  if (!apiKey || apiKey === 'sk-placeholder') return null;

  const provider = (process.env.DEEPSEEK_PROVIDER || 'deepseek').trim().toLowerCase();
  const model = process.env.DEEPSEEK_MODEL || 'deepseek-v4-flash';

  let baseUrl = process.env.DEEPSEEK_BASE_URL || '';
  if (!baseUrl) {
    baseUrl = provider === 'aliyun'
      ? 'https://llm-2prthk13jcdvsatm.cn-beijing.maas.aliyuncs.com/compatible-mode/v1'
      : 'https://api.deepseek.com/v1';
  }
  if (!baseUrl.endsWith('/v1') && !baseUrl.endsWith('/v2') && !baseUrl.includes('/compatible-mode/')) {
    baseUrl = baseUrl.replace(/\/$/, '') + '/v1';
  }

  return { apiKey, baseUrl, model };
}

async function main() {
  const config = resolveConfig();
  if (!config) { console.log('❌ 无有效 DeepSeek 配置'); process.exit(1); }

  const maskedKey = config.apiKey.slice(0, 12) + '...' + config.apiKey.slice(-4);
  console.log('当前配置:');
  console.log(`  DEEPSEEK_PROVIDER: ${process.env.DEEPSEEK_PROVIDER || '(未设=官方)'}`);
  console.log(`  API Key:           ${maskedKey}`);
  console.log(`  Base URL:          ${config.baseUrl}`);
  console.log(`  Model:             ${config.model}`);
  console.log(`  请求 URL:           ${config.baseUrl}/chat/completions`);
  console.log('');

  const prompt = '用中文回答："你是谁？"（20字以内）';

  try {
    console.log('发送测试请求...');
    const resp = await fetch(`${config.baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${config.apiKey}`,
      },
      body: JSON.stringify({
        model: config.model,
        messages: [{ role: 'user', content: prompt }],
        max_tokens: 50,
      }),
    });

    if (!resp.ok) {
      const errText = await resp.text();
      console.log(`❌ API 返回错误 ${resp.status}: ${errText.slice(0, 500)}`);
      console.log('');
      console.log('建议:');
      if (resp.status === 401 || resp.status === 403) {
        console.log('  - 检查 DEEPSEEK_API_KEY 是否正确');
      }
      if (resp.status === 404) {
        console.log('  - 检查 DEEPSEEK_BASE_URL 是否正确，阿里云应为: https://dashscope.aliyuncs.com/compatible-mode/v1');
        console.log('  - 或设置 DEEPSEEK_PROVIDER=aliyun 使用默认阿里云端点');
      }
      process.exit(1);
    }

    const data: any = await resp.json();
    const reply = data?.choices?.[0]?.message?.content || '(无回复)';
    console.log(`✅ 成功! 回复: "${reply}"`);
    console.log(`   Model: ${data?.model || '?'}`);
  } catch (err: any) {
    console.log(`❌ 网络错误: ${err.message}`);
    if (err.message.includes('ENOTFOUND') || err.message.includes('ECONNREFUSED')) {
      console.log('  无法连接到 API 服务器，检查网络和 DEEPSEEK_BASE_URL');
    }
  }
}

main().catch(e => { console.error(e); process.exit(1); });
