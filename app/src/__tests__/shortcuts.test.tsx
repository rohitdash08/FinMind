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

  it("navigates correctly on numeric and prefixed keys", () => {
    render(
      <BrowserRouter>
        <ShortcutTestComponent />
      </BrowserRouter>
    );

    const testCases = [
      { key: "1", path: "/dashboard" },
      { prefix: "g", key: "d", path: "/dashboard" },
      { key: "2", path: "/budgets" },
      { prefix: "g", key: "b", path: "/budgets" },
      { key: "3", path: "/bills" },
      { prefix: "g", key: "l", path: "/bills" },
      { key: "4", path: "/reminders" },
      { prefix: "g", key: "r", path: "/reminders" },
      { key: "5", path: "/expenses" },
      { prefix: "g", key: "e", path: "/expenses" },
      { key: "6", path: "/analytics" },
      { prefix: "g", key: "a", path: "/analytics" },
      { key: "7", path: "/account" },
      { prefix: "g", key: "c", path: "/account" },
    ];

    testCases.forEach((tc) => {
      useNavigateMock.mockClear();
      if (tc.prefix) {
        fireEvent.keyDown(window, { key: tc.prefix });
      }
      fireEvent.keyDown(window, { key: tc.key });
      expect(useNavigateMock).toHaveBeenCalledWith(tc.path);
    });
  });

  it("triggers logout on G+Q", () => {
    const dispatchSpy = jest.spyOn(window, 'dispatchEvent');
    render(
      <BrowserRouter>
        <ShortcutTestComponent />
      </BrowserRouter>
    );

    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "q" });
    
    // Find the fm_logout call among other event dispatches (like keydown)
    const logoutCall = dispatchSpy.mock.calls.find(call => 
      call[0] instanceof CustomEvent && call[0].type === 'fm_logout'
    );
    
    expect(logoutCall).toBeDefined();
    dispatchSpy.mockRestore();
  });

  it("toggles help modal on ?", () => {
    render(
      <BrowserRouter>
        <ShortcutTestComponent />
      </BrowserRouter>
    );

    expect(screen.getByTestId("help-status").textContent).toBe("closed");
    fireEvent.keyDown(window, { key: "?" });
    expect(screen.getByTestId("help-status").textContent).toBe("open");
    fireEvent.keyDown(window, { key: "?" });
    expect(screen.getByTestId("help-status").textContent).toBe("closed");
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

    fireEvent.keyDown(input, { key: "1" });
    expect(useNavigateMock).not.toHaveBeenCalled();

    fireEvent.keyDown(input, { key: "g" });
    fireEvent.keyDown(input, { key: "d" });
    expect(useNavigateMock).not.toHaveBeenCalled();
  });
});
