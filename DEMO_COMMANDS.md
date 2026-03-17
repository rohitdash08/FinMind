# Demo Instructions: Keyboard Shortcuts & Spending Heatmap

**🎥 View Demo:** [https://github.com/user-attachments/assets/c88a7103-9379-4b25-bbc1-5cb73cab4f62](https://github.com/user-attachments/assets/c88a7103-9379-4b25-bbc1-5cb73cab4f62)

These instructions guide you through demonstrating the features implemented in Issues #106 and #116.

## 1. Keyboard Shortcuts (Issue #106)
The application now supports global keyboard shortcuts for fast navigation and accessibility.

### How to Demo:
1.  **Open the Application:** Navigate to the FinMind dashboard in your browser.
2.  **Test Navigation:**
    *   Press `1` to jump to the **Dashboard**.
    *   Press `2` to jump to the **Budgets** page.
    *   Press `3` to jump to the **Bills** page.
    *   Press `4` to jump to the **Reminders** page.
    *   Press `5` to jump to the **Expenses** page.
    *   Press `6` to jump to the **Analytics** page.
    *   Press `7` to jump to the **Account** page.
    *   (Optionally, use `G` prefixes: `G+D`, `G+B`, `G+L`, `G+R`, `G+E`, `G+A`, `G+C`).
3.  **Logout:**
    *   Press `G` then `Q` to logout securely.
4.  **Show Shortcuts:**
    *   Press `Shift + ?` to open the **Keyboard Shortcuts Help Modal**.
    *   Verify that all shortcuts are listed with their descriptions and variants.
5.  **Test Accessibility:**
    *   Use the `Tab` key to navigate through interactive elements.
    *   Verify the high-contrast focus ring around focused elements.

---

## 2. Spending Trend Heatmap (Issue #116)
A GitHub-style heatmap provides a visual overview of spending intensity over the last 90 days.

### How to Demo:
1.  **Navigate to Analytics:** Use `6` or click on "Analytics" in the navbar.
2.  **View Heatmap:**
    *   The **Spending Intensity** card is now displayed at the top of the page.
3.  **Interactive Tooltips:**
    *   Hover over any square to see the exact date and the total amount spent on that day.
4.  **Theme Compatibility:**
    *   The heatmap colors adapt correctly to Light/Dark modes while maintaining visibility.

---

## 3. Automated Verification
Run the test suites to verify the logic:

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
