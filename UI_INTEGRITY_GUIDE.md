# Team Generator UI Integrity & Spacing Mandates

## 1. Zero Scrolling Policy
* All 10 input slots AND the Team Preview results MUST be visible on screen simultaneously without a scrollbar.
* Generator tab must remain a `ctk.CTkFrame`, never a `ctk.CTkScrollableFrame`.

## 2. Strict Dimensions
* **Window Size:** Vertical (~1000px height).
* **Player Input Slots:** Max 30px height (Current: 28px).
* **Action Buttons:** Max 45px height (Current: 40px).
* **Teams Preview Section:** Max 300px height (Current: 280px).
* **Team Name Slot (Result):** Max 30px height (Current: 25px).

## 3. UI Composition
* **Manage Players Button:** Prohibited at the bottom of the slots. Integrate into headers if needed.
* **Dropdown Buttons:** Must be present on every player name entry field.
* **Icons:** Must be theme-aware (Light vs Dark versions).
* **Corners:** Window Corner Radius must be 25-35 with transparent masking.

## 4. Spacing
* Keep vertical padding (`pady`) minimal (1-5px) between player slots and (10-15px) between main card sections.

Consult this guide BEFORE any UI-related modifications to avoid breaking the vertical fit.
