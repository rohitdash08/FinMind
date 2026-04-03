/**
 * Tests for keyboard-first navigation & shortcuts (issue #106).
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { KeyboardShortcutHelp } from "../components/KeyboardShortcutHelp";
import type { ShortcutConfig } from "../hooks/useKeyboardShortcuts";

const mockShortcuts: ShortcutConfig[] = [
  { key: "d", ctrl: true, description: "Go to Dashboard", action: jest.fn() },
  { key: "e", ctrl: true, description: "Go to Expenses", action: jest.fn() },
  { key: "b", ctrl: true, description: "Go to Bills", action: jest.fn() },
];

describe("KeyboardShortcutHelp", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <KeyboardShortcutHelp shortcuts={mockShortcuts} open={false} onClose={jest.fn()} />
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders shortcuts when open", () => {
    render(
      <KeyboardShortcutHelp shortcuts={mockShortcuts} open={true} onClose={jest.fn()} />
    );
    expect(screen.getByText("Go to Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Go to Expenses")).toBeInTheDocument();
    expect(screen.getByText("Go to Bills")).toBeInTheDocument();
  });

  it("calls onClose when close button clicked", () => {
    const onClose = jest.fn();
    render(
      <KeyboardShortcutHelp shortcuts={mockShortcuts} open={true} onClose={onClose} />
    );
    fireEvent.click(screen.getByLabelText("Close"));
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when backdrop clicked", () => {
    const onClose = jest.fn();
    render(
      <KeyboardShortcutHelp shortcuts={mockShortcuts} open={true} onClose={onClose} />
    );
    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalled();
  });

  it("does not close when dialog content clicked", () => {
    const onClose = jest.fn();
    render(
      <KeyboardShortcutHelp shortcuts={mockShortcuts} open={true} onClose={onClose} />
    );
    fireEvent.click(screen.getByText("Keyboard Shortcuts"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("shows platform-appropriate modifier key", () => {
    render(
      <KeyboardShortcutHelp shortcuts={mockShortcuts} open={true} onClose={jest.fn()} />
    );
    // Should show either Ctrl or ⌘ depending on platform
    const modifiers = screen.getAllByText(/Ctrl \+|⌘ \+/);
    expect(modifiers.length).toBeGreaterThan(0);
  });
});
