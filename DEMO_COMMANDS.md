# Demo Instructions: Keyboard Shortcuts & Spending Heatmap

These instructions guide you through demonstrating the features implemented in Issues #106 and #116.

## 1. Keyboard Shortcuts (Issue #106)
The application now supports global keyboard shortcuts for fast navigation and accessibility.

### How to Demo:
1.  **Open the Application:** Navigate to the FinMind dashboard in your browser.
2.  **Test Navigation:**
    *   Press `G` then `E` quickly to jump to the **Expenses** page.
    *   Press `G` then `A` to jump to the **Analytics** page.
    *   Press `G` then `B` to jump to the **Bills** page.
    *   Press `G` then `R` to jump to the **Reminders** page.
    *   Press `G` then `D` to return to the **Dashboard**.
3.  **Open Help Modal:**
    *   Press `?` (Shift + `/`) to open the **Keyboard Shortcuts Help Modal**.
    *   Verify that all shortcuts are listed with their descriptions.
    *   Close the modal using the `Esc` key or the close button.
4.  **Test Accessibility:**
    *   Use the `Tab` key to navigate through interactive elements.
    *   Verify that a high-contrast focus ring (primary color) appears around the focused element, meeting WCAG AA standards.

---

## 2. Spending Trend Heatmap (Issue #116)
A GitHub-style heatmap provides a visual overview of spending intensity over the last 90 days.

### How to Demo:
1.  **Navigate to Analytics:** Use `G + A` or click on "Analytics" in the navbar.
2.  **View Heatmap:**
    *   The **Spending Intensity** card is now displayed at the top of the page.
    *   Each square represents one day.
    *   **Colors:**
        *   `Muted/Gray`: No spending.
        *   `Light Green`: Low spending.
        *   `Dark Green`: High spending (relative to the maximum daily spend in the 90-day period).
3.  **Interactive Tooltips:**
    *   Hover over any square to see the exact date and the total amount spent on that day.
4.  **Theme Compatibility:**
    *   Toggle between Light and Dark modes.
    *   Verify that the heatmap colors adapt correctly to the theme while maintaining visibility.

---

## 3. Automated Verification
You can also run the automated test suites to verify the logic:

### Backend (Heatmap Logic)
```bash
cd packages/backend
PYTHONPATH=. .venv/bin/pytest tests/test_expenses_heatmap.py
```

### Frontend (Shortcuts Logic)
```bash
cd app
npm test src/__tests__/shortcuts.test.tsx
```
