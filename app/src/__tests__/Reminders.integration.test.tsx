import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Reminders from '@/pages/Reminders';

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
jest.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}));
jest.mock('@/components/ui/alert-dailog', () => ({
  AlertDialog: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  AlertDialogAction: ({ children, ...props }: React.PropsWithChildren & React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}));

const listRemindersMock = jest.fn();
const createReminderMock = jest.fn();
const deleteReminderMock = jest.fn();
const runDueMock = jest.fn();
const scheduleBillRemindersMock = jest.fn();
const reportAutopayResultMock = jest.fn();
jest.mock('@/api/reminders', () => ({
  listReminders: (...args: unknown[]) => listRemindersMock(...args),
  createReminder: (...args: unknown[]) => createReminderMock(...args),
  deleteReminder: (...args: unknown[]) => deleteReminderMock(...args),
  runDue: (...args: unknown[]) => runDueMock(...args),
  scheduleBillReminders: (...args: unknown[]) => scheduleBillRemindersMock(...args),
  reportAutopayResult: (...args: unknown[]) => reportAutopayResultMock(...args),
}));

const listBillsMock = jest.fn();
jest.mock('@/api/bills', () => ({
  listBills: (...args: unknown[]) => listBillsMock(...args),
}));

describe('Reminders integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    listRemindersMock.mockResolvedValue([]);
    listBillsMock.mockResolvedValue([
      { id: 1, name: 'Electricity', autopay_enabled: true, channel_email: true, channel_whatsapp: true },
    ]);
    scheduleBillRemindersMock.mockResolvedValue({ created: 6 });
    reportAutopayResultMock.mockResolvedValue({ created: 2 });
    createReminderMock.mockResolvedValue({ id: 10 });
    deleteReminderMock.mockResolvedValue({});
    runDueMock.mockResolvedValue({ processed: 0 });
  });

  it('schedules bill reminders from bill scheduler panel', async () => {
    render(<Reminders />);
    await waitFor(() => expect(listBillsMock).toHaveBeenCalled());
    await screen.findByText(/smart bill scheduling/i);

    await userEvent.type(screen.getByLabelText(/reminder offsets/i), '7,3,1');
    await userEvent.click(screen.getByRole('button', { name: /schedule bill reminders/i }));

    await waitFor(() => expect(scheduleBillRemindersMock).toHaveBeenCalled());
    expect(scheduleBillRemindersMock).toHaveBeenCalledWith(1, [7, 3, 1]);
  });

  it('sends autopay result follow-up', async () => {
    render(<Reminders />);
    await waitFor(() => expect(listBillsMock).toHaveBeenCalled());
    await screen.findByText(/smart bill scheduling/i);

    await userEvent.click(screen.getByRole('button', { name: /autopay success/i }));
    await waitFor(() => expect(reportAutopayResultMock).toHaveBeenCalledWith(1, 'SUCCESS'));
  });
});
