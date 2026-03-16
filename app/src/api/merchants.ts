import api from "./index";

export interface MerchantAliasItem {
  id: number;
  alias: string;
  created_at: string;
}

export interface Merchant {
  id: number;
  canonical_name: string;
  aliases: MerchantAliasItem[];
  created_at: string;
}

export interface SuggestResponse {
  suggestions: string[];
  query: string;
}

export async function listMerchants(q?: string): Promise<Merchant[]> {
  const { data } = await api.get<Merchant[]>("/merchants", {
    params: q ? { q } : undefined,
  });
  return data;
}

export async function createMerchant(
  canonical_name: string,
  aliases?: string[]
): Promise<Merchant> {
  const { data } = await api.post<Merchant>("/merchants", {
    canonical_name,
    aliases,
  });
  return data;
}

export async function getMerchant(id: number): Promise<Merchant> {
  const { data } = await api.get<Merchant>(`/merchants/${id}`);
  return data;
}

export async function updateMerchant(
  id: number,
  canonical_name: string
): Promise<Merchant> {
  const { data } = await api.patch<Merchant>(`/merchants/${id}`, {
    canonical_name,
  });
  return data;
}

export async function deleteMerchant(id: number): Promise<void> {
  await api.delete(`/merchants/${id}`);
}

export async function addAlias(
  merchantId: number,
  alias: string
): Promise<Merchant> {
  const { data } = await api.post<Merchant>(
    `/merchants/${merchantId}/aliases`,
    { alias }
  );
  return data;
}

export async function removeAlias(
  merchantId: number,
  aliasId: number
): Promise<Merchant> {
  const { data } = await api.delete<Merchant>(
    `/merchants/${merchantId}/aliases/${aliasId}`
  );
  return data;
}

export async function mergeMerchants(
  targetId: number,
  sourceId: number
): Promise<Merchant> {
  const { data } = await api.post<Merchant>("/merchants/merge", {
    target_id: targetId,
    source_id: sourceId,
  });
  return data;
}

export async function suggestMerchants(
  q: string,
  limit = 10
): Promise<SuggestResponse> {
  const { data } = await api.get<SuggestResponse>("/merchants/suggest", {
    params: { q, limit },
  });
  return data;
}
