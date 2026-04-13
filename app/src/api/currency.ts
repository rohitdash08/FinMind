import { api } from './client';

export type ConversionResult = {
  amount: number; from: string; to: string; rate: number; converted: number;
};

export async function getSupportedCurrencies(): Promise<{ currencies: string[] }> {
  return api('/currency/supported');
}

export async function convertCurrency(amount: number, from: string, to: string): Promise<ConversionResult> {
  return api(`/currency/convert?amount=${amount}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`);
}

export async function convertAll(amount: number, from: string): Promise<{ conversions: ConversionResult[]; base_amount: number; base_currency: string }> {
  return api(`/currency/convert-all?amount=${amount}&from=${encodeURIComponent(from)}`);
}
