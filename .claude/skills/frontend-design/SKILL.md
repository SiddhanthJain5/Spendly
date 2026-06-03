---
name: spendly-ui
description: >
  Generates modern, production-ready UI pages and components for Spendly — a personal expense tracker built with Flask, Jinja2, and vanilla CSS/JS. Outputs clean HTML templates (extending base.html), matching CSS, and optional JS. Always trigger this skill when the user says "design a ___ page", "build a UI for ___", "build a component for ___", "redesign ___", or "rebuild ___" in the context of Spendly or any expense tracker UI. Also trigger for any request to improve, polish, or extend Spendly's frontend, even if the phrase "skill" or "design" isn't used.
---

# Spendly UI Skill

Produce polished, production-grade frontend pages and components for Spendly. Output is drop-in ready: Jinja2 HTML that extends `base.html`, scoped CSS, and minimal vanilla JS where needed.

---

## Project Context

**Stack**: Python/Flask · SQLite · Jinja2 templates · Vanilla CSS + JS  
**Repo**: https://github.com/SiddhanthJain5/Spendly  
**Template structure**: All pages extend `templates/base.html` (navbar, footer, script blocks).  
**CSS files**:
- `static/css/style.css` — shared styles: navbar, footer, base typography, buttons
- `static/css/landing.css` — landing-page-only styles

**Pages that exist**: landing, register, login, terms, privacy  
**Pages stubbed (need UI)**: profile, add_expense, edit_expense, delete confirmation, dashboard/expense list

---

## Design System

Apply these consistently across every output:

### Color Palette
```css
--primary:       #6C63FF;   /* indigo-violet — main CTAs, active states */
--primary-dark:  #574fd6;   /* hover/pressed */
--accent:        #FF6584;   /* danger, delete, negative amounts */
--success:       #43D98F;   /* income, savings, positive states */
--warning:       #FFB347;   /* budget alerts, approaching limits */
--bg:            #F8F9FF;   /* page background */
--surface:       #FFFFFF;   /* cards, modals, inputs */
--surface-alt:   #F1F2FB;   /* zebra rows, subtle section bg */
--text-primary:  #1A1A2E;   /* headings */
--text-secondary:#6B7280;   /* labels, captions */
--border:        #E5E7EB;   /* dividers, input borders */
--shadow-sm:     0 1px 3px rgba(108,99,255,0.08);
--shadow-md:     0 4px 16px rgba(108,99,255,0.12);
--shadow-lg:     0 8px 32px rgba(108,99,255,0.16);
--radius-sm:     8px;
--radius-md:     12px;
--radius-lg:     20px;
```

### Typography
- Font: `'Inter', system-ui, sans-serif` (load from Google Fonts)
- Scale: 12 / 14 / 16 / 18 / 24 / 32 / 48px
- Headings: weight 700, text-primary
- Body: weight 400–500, text-secondary
- Labels/caps: weight 600, letter-spacing 0.5px, uppercase

### Spacing
- Base unit: 4px. Use multiples: 8, 12, 16, 20, 24, 32, 48, 64
- Section padding: 48px vertical on desktop, 32px on mobile
- Card padding: 24px desktop, 16px mobile

### Iconography
Use **Lucide Icons** via CDN:
```html
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
```
Then: `<i data-lucide="wallet"></i>` + call `lucide.createIcons()` at end of body.

**Icon map for Spendly:**
- wallet → total balance / brand
- trending-up → income / growth
- trending-down → expense / spending
- pie-chart → analytics / breakdown
- plus-circle → add expense
- edit-2 → edit
- trash-2 → delete
- filter → filter/sort
- calendar → date
- tag → category
- receipt → transaction/expense item
- shield-check → savings goal / budget
- bell → notifications
- user → profile
- log-out → logout
- home → dashboard
- search → search
- chevron-right / chevron-down → navigation

### Component Patterns

**Cards**
```css
.card {
  background: var(--surface);
  border-radius: var(--radius-md);
  padding: 24px;
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border);
}
.card:hover { box-shadow: var(--shadow-md); transform: translateY(-1px); transition: all 0.2s; }
```

**Stat Cards** (used on dashboard/profile)
- Icon in a soft-colored circle (tinted version of semantic color)
- Large bold number, label below, optional trend badge

**Buttons**
```css
.btn-primary   { background: var(--primary); color: #fff; }
.btn-secondary { background: var(--surface-alt); color: var(--text-primary); border: 1px solid var(--border); }
.btn-danger    { background: var(--accent); color: #fff; }
/* All buttons: border-radius 8px, padding 10px 20px, font-weight 600, transition 0.2s */
```

**Form Inputs**
```css
.form-input {
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  font-size: 15px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.form-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(108,99,255,0.12);
  outline: none;
}
```

**Tags / Category Badges**
- Pill shape, soft background (10% opacity of category color), matching text
- Categories: Food 🍕 (#FF6B6B), Transport 🚗 (#4ECDC4), Shopping 🛍️ (#FFE66D), Entertainment 🎬 (#A8E6CF), Health 💊 (#FF8B94), Utilities ⚡ (#85C1E9), Other 📦 (#C39BD3)

**Empty States**
- Centered illustration (inline SVG, simple and minimal), heading, subtext, CTA button
- Never leave a blank section — always show a friendly empty state

**Expense Table / List**
- Prefer a card-based list over a plain `<table>` on mobile
- Each row: category icon · merchant/title · date · category badge · amount (red for expense, green for income)
- On desktop, can use a proper `<table>` with zebra rows

---

## Output Format

For each request, produce:

1. **HTML** — Jinja2 template that starts with `{% extends "base.html" %}` and uses `{% block content %}` ... `{% endblock %}`. Add `{% block head %}` for page-specific CSS link.
2. **CSS** — A new file e.g. `static/css/profile.css` with scoped styles. Import Inter font at the top if not already in base.
3. **JS** (only if needed) — Minimal vanilla JS, no frameworks. Annotate clearly.
4. **Route stub** — Show the Flask route to add/update in `app.py` (just the snippet, not the whole file).

Always include:
- `<link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">` awareness (it's in base)
- `lucide.createIcons()` at bottom of body or in a `{% block scripts %}` block
- Responsive breakpoints: mobile-first, `@media (min-width: 768px)` for desktop enhancements

---

## Page-Specific Guidelines

### Profile Page (`/profile`)
- Header: avatar circle (initials), name, email, member since
- Stats row: Total Spent, This Month, Top Category, # Transactions
- Recent transactions preview (last 5)
- Quick actions: Add Expense, View All, Edit Profile

### Dashboard / Expense List (`/dashboard` or `/expenses`)
- Summary bar: Total balance, income, expenses
- Filters: date range, category, search
- Expense list/table with pagination
- Floating "+ Add" button (fixed bottom-right on mobile)

### Add / Edit Expense (`/expenses/add`, `/expenses/<id>/edit`)
- Clean single-column form
- Fields: Title, Amount, Category (visual pill selector), Date, Notes (optional)
- Preview card showing what the entry will look like
- Cancel / Save buttons

### Delete Confirmation
- Modal overlay (not a full page)
- Show the expense being deleted
- "Delete" (danger) + "Cancel" buttons

### Landing Page enhancements
- Hero: bold tagline, subhead, CTA pair (Get Started, See Demo)
- Feature cards: 3 columns, icon + title + description
- Social proof / mockup screenshot section

---

## Quality Checklist

Before finalising output, verify:
- [ ] Consistent use of CSS variables (no hardcoded hex colors)
- [ ] All icons use Lucide, not emoji (except category badges which can mix)
- [ ] Mobile-first responsive layout
- [ ] Hover/focus states on all interactive elements
- [ ] Empty states handled
- [ ] Flash message area for Flask `get_flashed_messages()`
- [ ] Jinja2 template syntax is valid (`{% %}`, `{{ }}`)
- [ ] No inline styles except for dynamic values (e.g. `style="width: {{ pct }}%"`)
- [ ] Accessibility: `aria-label` on icon-only buttons, proper `<label for="">` on inputs

---

## References

- See `references/existing-pages.md` for notes on the landing and auth pages' existing patterns.
- See `references/component-library.md` for copy-paste component snippets.