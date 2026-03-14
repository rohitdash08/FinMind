import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Jobs from '@/pages/Jobs';

const toastMock = jest.fn();
jest.mock('@/hooks/use-toast', () => ({
  useToast: () => ({ toast: toastMock }),
}));

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}));
jest.mock('@/components/ui/input', () => ({
  Input: ({ ...props }: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));
jest.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.PropsWithChildren & React.LabelHTMLAttributes<HTMLLabelElement>) => (
    <label {...props}>{children}</label>
  ),
}));
jest.mock('@/components/ui/badge', () => ({
  Badge: ({ children, className, ...props }: React.PropsWithChildren & React.HTMLAttributes<HTMLDivElement>) => (
    <span className={className} {...props}>{children}</span>
  ),
}));
jest.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));

const listJobsMock = jest.fn();
const createJobMock = jest.fn();
const retryJobMock = jest.fn();
const getJobStatsMock = jest.fn();
const getDeadLetterQueueMock = jest.fn();
jest.mock('@/api/jobs', () => ({
  listJobs: (...args: unknown[]) => listJobsMock(...args),
  createJob: (...args: unknown[]) => createJobMock(...args),
  retryJob: (...args: unknown[]) => retryJobMock(...args),
  getJobStats: (...args: unknown[]) => getJobStatsMock(...args),
  getDeadLetterQueue: (...args: unknown[]) => getDeadLetterQueueMock(...args),
}));

const SAMPLE_JOB = {
  id: 1,
  user_id: 1,
  name: 'Sync bank data',
  job_type: 'DATA_SYNC' as const,
  status: 'COMPLETED' as const,
  attempts: 1,
  max_retries: 5,
  last_error: null,
  payload: '{"source":"plaid"}',
  result: '{"records_synced":42}',
  scheduled_at: '2025-01-01T00:00:00',
  started_at: '2025-01-01T00:00:01',
  completed_at: '2025-01-01T00:00:02',
  next_retry_at: null,
  created_at: '2025-01-01T00:00:00',
  updated_at: '2025-01-01T00:00:02',
};

const FAILED_JOB = {
  ...SAMPLE_JOB,
  id: 2,
  name: 'Failed report',
  job_type: 'REPORT_GENERATION' as const,
  status: 'FAILED' as const,
  attempts: 3,
  last_error: 'Connection timeout',
  completed_at: null,
  result: null,
  next_retry_at: '2025-01-01T00:01:00',
};

const SAMPLE_STATS = {
  pending: 2,
  running: 1,
  completed: 10,
  failed: 3,
  dead: 1,
  total: 17,
};

describe('Jobs monitor integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    listJobsMock.mockResolvedValue({
      jobs: [SAMPLE_JOB, FAILED_JOB],
      total: 2,
      page: 1,
      per_page: 20,
    });
    getJobStatsMock.mockResolvedValue(SAMPLE_STATS);
    createJobMock.mockResolvedValue(SAMPLE_JOB);
    retryJobMock.mockResolvedValue({ ...FAILED_JOB, status: 'COMPLETED', attempts: 4 });
    getDeadLetterQueueMock.mockResolvedValue([]);
  });

  it('renders page title and stats cards', async () => {
    render(<Jobs />);
    await waitFor(() => expect(getJobStatsMock).toHaveBeenCalled());
    expect(screen.getByText(/background jobs/i)).toBeInTheDocument();
    expect(screen.getByText('17')).toBeInTheDocument(); // total
    expect(screen.getByText('10')).toBeInTheDocument(); // completed
  });

  it('renders job list with status badges', async () => {
    render(<Jobs />);
    await waitFor(() => expect(listJobsMock).toHaveBeenCalled());
    expect(screen.getByText('Sync bank data')).toBeInTheDocument();
    expect(screen.getByText('Failed report')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('shows retry button for failed jobs', async () => {
    render(<Jobs />);
    await waitFor(() => expect(listJobsMock).toHaveBeenCalled());
    const retryButtons = screen.getAllByRole('button', { name: /retry/i });
    expect(retryButtons.length).toBeGreaterThanOrEqual(1);
  });

  it('retries a failed job', async () => {
    render(<Jobs />);
    await waitFor(() => expect(listJobsMock).toHaveBeenCalled());
    const retryButtons = screen.getAllByRole('button', { name: /retry/i });
    await userEvent.click(retryButtons[0]);
    await waitFor(() => expect(retryJobMock).toHaveBeenCalledWith(2));
    expect(toastMock).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Job retried' }),
    );
  });

  it('shows error message for failed jobs', async () => {
    render(<Jobs />);
    await waitFor(() => expect(listJobsMock).toHaveBeenCalled());
    expect(screen.getByText('Connection timeout')).toBeInTheDocument();
  });

  it('displays attempt counter', async () => {
    render(<Jobs />);
    await waitFor(() => expect(listJobsMock).toHaveBeenCalled());
    expect(screen.getByText('Attempt 1/5')).toBeInTheDocument();
    expect(screen.getByText('Attempt 3/5')).toBeInTheDocument();
  });

  it('shows empty state when no jobs', async () => {
    listJobsMock.mockResolvedValue({ jobs: [], total: 0, page: 1, per_page: 20 });
    getJobStatsMock.mockResolvedValue({ ...SAMPLE_STATS, total: 0 });
    render(<Jobs />);
    await waitFor(() => expect(listJobsMock).toHaveBeenCalled());
    expect(screen.getByText(/no jobs found/i)).toBeInTheDocument();
  });
});
