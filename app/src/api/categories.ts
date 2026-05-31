import { api } from './client';

export type Category = { id: number; name: string };

export async function listCategories(): Promise<Category[]> {
  return api<Category[]>('/categories');
}

export async function createCategory(name: string): Promise<Category> {
  return api<Category>('/categories', { method: 'POST', body: { name } });
}

export async function updateCategory(id: number, name: string): Promise<Category> {
  return api<Category>(`/categories/${id}`, { method: 'PATCH', body: { name } });
}

export async function deleteCategory(id: number): Promise<{ message?: string } | { message: string }> {
  return api(`/categories/${id}`, { method: 'DELETE' });
}
