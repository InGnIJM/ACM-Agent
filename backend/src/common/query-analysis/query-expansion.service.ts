import { Injectable, Logger } from '@nestjs/common';

export interface ExpandedQuery {
  /** 原始用户输入 */
  rawQuery: string;
  /** 识别出的用户意图 */
  intent: 'find_similar' | 'learn_algorithm' | 'debug_error' | 'find_by_topic' | 'unknown';
  /** 提取的算法/数据结构术语（中英文） */
  algorithmTerms: string[];
  /** 扩写后的完整查询（用于 embedding） */
  expandedForEmbedding: string;
  /** 关键词列表（用于全文搜索） */
  keywords: string[];
  /** 建议的过滤条件 */
  suggestedFilters: {
    difficulty?: 'easy' | 'medium' | 'hard';
    tags?: string[];
  };
}

const SYSTEM_PROMPT = `你是一个竞赛算法搜索助手。用户会输入一个搜索词或描述，你需要：

1. **识别意图**：用户想找什么？
   - find_similar: 找类似的题目练习
   - learn_algorithm: 想学习某种算法
   - debug_error: 某道题做不出来，想找类似题理解
   - find_by_topic: 按知识点/标签找题
   - unknown: 无法判断

2. **提取算法术语**：涉及的算法、数据结构、解题技巧（中英文都要）

3. **扩写查询**：将用户的自然语言描述转化为更适合向量检索的文本，包含：
   - 核心算法名称
   - 典型问题模式（如"区间最值"、"最短路径"、"子序列"）
   - 关键约束条件（如"有序数组"、"无环图"、"非负权"）

4. **提取关键词**：用于精确匹配的关键词

5. **建议过滤条件**：如果能判断难度或标签，提供建议

**重要**：只返回 JSON，不要解释。`;

function buildUserPrompt(query: string, dictTerms: string[]): string {
  const dictHint = dictTerms.length > 0
    ? `\n已匹配的字典术语：${dictTerms.join(', ')}`
    : '';
  return `搜索词：${query}${dictHint}

返回 JSON 格式：
{
  "intent": "find_similar|learn_algorithm|debug_error|find_by_topic|unknown",
  "algorithmTerms": ["算法1", "algorithm2", ...],
  "expandedForEmbedding": "扩写后的完整查询文本",
  "keywords": ["关键词1", "关键词2", ...],
  "suggestedFilters": {
    "difficulty": "easy|medium|hard|null",
    "tags": ["tag1", "tag2"]
  }
}`;
}

@Injectable()
export class QueryExpansionService {
  private readonly logger = new Logger(QueryExpansionService.name);

  /**
   * Expand a user query using LLM + dictionary.
   *
   * @param query     Raw user input
   * @param dictTerms Algorithm terms already matched by dictionary
   * @returns         Structured expansion, or null if LLM unavailable
   */
  async expand(query: string, dictTerms: string[] = []): Promise<ExpandedQuery | null> {
    const apiKey = (process.env.DEEPSEEK_API_KEY || '').trim();
    if (!apiKey || apiKey === 'sk-placeholder') return null;

    const baseUrl = process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com/v1';
    const model = process.env.DEEPSEEK_MODEL || 'deepseek-v4-flash';

    try {
      const resp = await fetch(`${baseUrl}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model,
          messages: [
            { role: 'system', content: SYSTEM_PROMPT },
            { role: 'user', content: buildUserPrompt(query, dictTerms) },
          ],
          temperature: 0.1,
          max_tokens: 500,
          thinking: { type: 'disabled' },
          response_format: { type: 'json_object' },
        }),
        signal: AbortSignal.timeout(5000),
      });

      if (!resp.ok) {
        this.logger.warn(`LLM expansion failed: HTTP ${resp.status}`);
        return null;
      }

      const data: any = await resp.json();
      const text = data?.choices?.[0]?.message?.content?.trim();
      if (!text) return null;

      const parsed = JSON.parse(text);
      return this.validate(parsed, query, dictTerms);
    } catch (err: any) {
      this.logger.warn(`LLM expansion error: ${err.message}`);
      return null;
    }
  }

  /** Validate and sanitize LLM output. */
  private validate(raw: any, query: string, dictTerms: string[]): ExpandedQuery {
    const intent = ['find_similar', 'learn_algorithm', 'debug_error', 'find_by_topic'].includes(raw.intent)
      ? raw.intent
      : 'unknown';

    const algorithmTerms = [
      ...new Set([
        ...dictTerms,
        ...(Array.isArray(raw.algorithmTerms) ? raw.algorithmTerms.filter((t: any) => typeof t === 'string' && t.length > 1) : []),
      ]),
    ];

    const keywords = [
      ...new Set([
        ...algorithmTerms,
        ...(Array.isArray(raw.keywords) ? raw.keywords.filter((k: any) => typeof k === 'string' && k.length > 1) : []),
      ]),
    ];

    // expandedForEmbedding: prefer LLM output, fallback to query + terms
    let expandedForEmbedding = typeof raw.expandedForEmbedding === 'string' && raw.expandedForEmbedding.length > 5
      ? raw.expandedForEmbedding
      : `${query} ${algorithmTerms.join(' ')}`;

    // Cap length to avoid embedding truncation
    if (expandedForEmbedding.length > 500) {
      expandedForEmbedding = expandedForEmbedding.slice(0, 500);
    }

    const suggestedFilters: ExpandedQuery['suggestedFilters'] = {};
    if (['easy', 'medium', 'hard'].includes(raw.suggestedFilters?.difficulty)) {
      suggestedFilters.difficulty = raw.suggestedFilters.difficulty;
    }
    if (Array.isArray(raw.suggestedFilters?.tags)) {
      suggestedFilters.tags = raw.suggestedFilters.tags.filter((t: any) => typeof t === 'string');
    }

    return {
      rawQuery: query,
      intent,
      algorithmTerms,
      expandedForEmbedding,
      keywords,
      suggestedFilters,
    };
  }
}
