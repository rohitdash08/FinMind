import { useState, useEffect, useCallback } from 'react';
import { FinancialCard, FinancialCardContent, FinancialCardHeader, FinancialCardTitle } from '@/components/ui/financial-card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { FileText, RefreshCw, Lightbulb, TrendingUp, Calendar } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { getLatestDigest, getDigestHistory, generateDigest, type WeeklyDigest } from '@/api/digest';

export default function Digest() {
  const { toast } = useToast();
  const [latest, setLatest] = useState<WeeklyDigest | null>(null);
  const [history, setHistory] = useState<WeeklyDigest[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [lat, hist] = await Promise.allSettled([getLatestDigest(), getDigestHistory()]);
      if (lat.status === 'fulfilled') setLatest(lat.value);
      if (hist.status === 'fulfilled') setHistory(hist.value);
    } catch {
      // No digest yet is fine
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const d = await generateDigest();
      setLatest(d);
      toast({ title: 'Digest generated!' });
      loadData();
    } catch (e: unknown) {
      toast({ title: 'Error', description: e instanceof Error ? e.message : 'No transactions for last week', variant: 'destructive' });
    } finally { setGenerating(false); }
  };

  if (loading) return <div className="flex justify-center p-8">Loading...</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Weekly Digest</h1>
          <p className="text-muted-foreground">Your weekly financial summary and insights</p>
        </div>
        <Button onClick={handleGenerate} disabled={generating}>
          <RefreshCw className={`mr-2 h-4 w-4 ${generating ? 'animate-spin' : ''}`} />
          {generating ? 'Generating...' : 'Generate Digest'}
        </Button>
      </div>

      {latest ? (
        <FinancialCard>
          <FinancialCardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                <FinancialCardTitle>
                  Week of {latest.week_start} to {latest.week_end}
                </FinancialCardTitle>
              </div>
              <Badge variant="outline">{latest.method}</Badge>
            </div>
          </FinancialCardHeader>
          <FinancialCardContent className="space-y-4">
            {/* Summary */}
            <div className="whitespace-pre-line text-sm">{latest.summary}</div>

            {/* Tips */}
            {latest.tips.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-sm font-semibold flex items-center gap-1">
                  <Lightbulb className="h-4 w-4 text-yellow-500" /> Tips
                </h3>
                <ul className="space-y-1">
                  {latest.tips.map((tip, i) => (
                    <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                      <span className="text-yellow-500">•</span> {tip}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Highlights */}
            {latest.highlights.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-sm font-semibold flex items-center gap-1">
                  <TrendingUp className="h-4 w-4 text-green-500" /> Highlights
                </h3>
                <ul className="space-y-1">
                  {latest.highlights.map((h, i) => (
                    <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                      <span className="text-green-500">•</span> {h}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </FinancialCardContent>
        </FinancialCard>
      ) : (
        <FinancialCard>
          <FinancialCardContent className="flex flex-col items-center justify-center py-12">
            <FileText className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground mb-4">No digest yet. Add some expenses and generate your first weekly digest!</p>
            <Button onClick={handleGenerate} disabled={generating}>
              <RefreshCw className={`mr-2 h-4 w-4 ${generating ? 'animate-spin' : ''}`} />
              Generate Now
            </Button>
          </FinancialCardContent>
        </FinancialCard>
      )}

      {/* History */}
      {history.length > 1 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Calendar className="h-5 w-5" /> Previous Digests
          </h2>
          {history.slice(1).map(d => (
            <FinancialCard key={d.id}>
              <FinancialCardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <FinancialCardTitle className="text-sm">
                    {d.week_start} — {d.week_end}
                  </FinancialCardTitle>
                  <Badge variant="outline" className="text-xs">{d.method}</Badge>
                </div>
              </FinancialCardHeader>
              <FinancialCardContent>
                <p className="text-sm text-muted-foreground line-clamp-3">{d.summary}</p>
              </FinancialCardContent>
            </FinancialCard>
          ))}
        </div>
      )}
    </div>
  );
}
