import { api } from './client';

export type NLQueryResponse = {
  answer: string;
  data: Record<string, unknown>;
  pattern: string | null;
  question: string;
};

export async function queryFinance(question: string): Promise<NLQueryResponse> {
  return api<NLQueryResponse>('/query', {
    method: 'POST',
    body: { question },
  });
}
