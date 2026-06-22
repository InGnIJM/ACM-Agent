import { Injectable } from '@nestjs/common';
import * as fs from 'fs';
import * as path from 'path';

export interface RetrievalWeights {
  content: number;
  solution: number;
  keyword: number;
}

export interface QueryAnalysisResult {
  rawQuery: string;
  queryType: 'problem_semantic' | 'algorithm_intent' | 'error_reason' | 'mixed';
  expandedQuery: string;
  keywords: string[];
  algorithmTerms: string[];
  problemPatterns: string[];
  queryTags: string[];
  weights: RetrievalWeights;
}

type AlgoDict = Record<string, string[]>;

const WEIGHTS: Record<string, RetrievalWeights> = {
  problem_semantic: { content: 0.60, solution: 0.30, keyword: 0.10 },
  algorithm_intent: { content: 0.20, solution: 0.55, keyword: 0.25 },
  error_reason:     { content: 0.20, solution: 0.60, keyword: 0.20 },
};

const ERROR_PATTERNS: RegExp[] = [
  /为什么.*(错|不对|过不了|WA|TLE)/,
  /怎么(处理|避免|防止)/,
  /容易(错|出错)/,
  /(忘记|没注意|忽略了?)/,
  /(恢复|回溯).*(状态|现场)/,
  /边界.*(错|不对)/,
  /哪里(错了|不对|有问题)/,
];

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function matchAlgorithmTerms(query: string, dict: AlgoDict): string[] {
  const matched: string[] = [];
  for (const [algo, aliases] of Object.entries(dict)) {
    const allTerms = [algo, ...aliases];
    for (const term of allTerms) {
      let found = false;
      if (/[一-鿿]/.test(term)) {
        found = query.includes(term);
      } else {
        found = new RegExp(`\\b${escapeRegex(term)}\\b`, 'i').test(query);
      }
      if (found) {
        matched.push(algo);
        break;
      }
    }
  }
  return [...new Set(matched)];
}

@Injectable()
export class QueryAnalysisService {
  private readonly dict: AlgoDict;

  constructor() {
    const dictPath = path.join(__dirname, 'query_expansion.json');
    this.dict = JSON.parse(fs.readFileSync(dictPath, 'utf-8'));
  }

  analyze(rawQuery: string): QueryAnalysisResult {
    const query = rawQuery.trim();
    if (!query || query.length < 2) {
      throw new Error('查询内容过短，至少输入 2 个字符');
    }

    const algorithmTerms = matchAlgorithmTerms(query, this.dict);
    const hasErrorIntent = ERROR_PATTERNS.some(p => p.test(query));

    let queryType: QueryAnalysisResult['queryType'];
    if (algorithmTerms.length === 0 && !hasErrorIntent) {
      queryType = 'problem_semantic';
    } else if (hasErrorIntent) {
      queryType = 'error_reason';
    } else {
      queryType = 'algorithm_intent';
    }

    const expandedParts: string[] = [query];
    const allAliases: string[] = [];
    for (const term of algorithmTerms) {
      const aliases = this.dict[term] || [];
      allAliases.push(...aliases);
    }
    const uniqueAliases = [...new Set(allAliases)].filter(a => !query.includes(a));
    expandedParts.push(...uniqueAliases.slice(0, 10));

    return {
      rawQuery: query,
      queryType,
      expandedQuery: expandedParts.join(' '),
      keywords: [...algorithmTerms, ...uniqueAliases],
      algorithmTerms,
      problemPatterns: [],
      queryTags: algorithmTerms,
      weights: { ...WEIGHTS[queryType] },
    };
  }
}
