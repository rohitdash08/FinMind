import { render, screen, act, fireEvent } from "@testing-library/react";
import { useShortcuts } from "../hooks/use-shortcuts";
import { BrowserRouter } from "react-router-dom";
import React from "react";

const useNavigateMock = jest.fn();
jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => useNavigateMock,
}));

const ShortcutTestComponent = () => {
  const { isHelpOpen } = useShortcuts();
  return (
    <div>
      <div data-testid="help-status">{isHelpOpen ? "open" : "closed"}</div>
    </div>
  );
};

describe("useShortcuts", () => {
  beforeEach(() => {
    useNavigateMock.mockClear();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("navigates to dashboard on G+D", () => {
    render(
      <BrowserRouter>
        <ShortcutTestComponent />
      </BrowserRouter>
    );

    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "d" });

    expect(useNavigateMock).toHaveBeenCalledWith("/dashboard");
  });

  it("navigates to expenses on G+E", () => {
    render(
      <BrowserRouter>
        <ShortcutTestComponent />
      </BrowserRouter>
    );

    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "e" });

    expect(useNavigateMock).toHaveBeenCalledWith("/expenses");
  });

  it("opens help modal on ?", () => {
    render(
      <BrowserRouter>
        <ShortcutTestComponent />
      </BrowserRouter>
    );

    expect(screen.getByTestId("help-status").textContent).toBe("closed");

    fireEvent.keyDown(window, { key: "?" });

    expect(screen.getByTestId("help-status").textContent).toBe("open");
  });

  it("ignores shortcuts when typing in inputs", () => {
    render(
      <BrowserRouter>
        <ShortcutTestComponent />
        <input data-testid="test-input" />
      </BrowserRouter>
    );

    const input = screen.getByTestId("test-input");
    input.focus();

    fireEvent.keyDown(input, { key: "g" });
    fireEvent.keyDown(input, { key: "d" });

    expect(useNavigateMock).not.toHaveBeenCalled();
  });
});
