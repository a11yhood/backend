# Accessibility

This repository is the a11yhood backend (a Python/FastAPI API). Most of what people see and use is in the website. The main accessibility statement, our standard (WCAG 2.2 Level AA), severity levels, etc are in the frontend repository:

**[a11yhood.github.io: ACCESSIBILITY.md](https://github.com/a11yhood/a11yhood.github.io/blob/main/ACCESSIBILITY.md)**

## What accessibility means for the backend

The backend affects accessibility through content it sends to people and to the website:

- **Error messages** are clear, in plain language, and actionable. The website shows many of them to users.
- **Generated content**, such as emails (for example request notifications), has a plain-text part, descriptive subject lines, meaningful link text, and does not rely on color or images alone.
- **Data fields** that feed the website's accessible interface (alt text, titles, descriptions) are required or clearly supported where the website needs them.
- **Documentation** (README, API docs, guides) uses headings, descriptive links, and text alternatives for images and diagrams.

## Report a barrier

- Open an [accessibility issue](https://github.com/a11yhood/backend/issues/new?template=accessibility.yml), or
- email **create-contact@uw.edu** if GitHub is hard to use or you prefer not to post publicly.

We are a small team and cannot promise a response time, but someone reads every report. See the frontend statement for more on what to expect.

## Contributing

- Check user-facing text you add (errors, emails, docs) for clear, plain language and for how it reads with a screen reader.
- Complete the accessibility section of the pull request template.
- Contribution guidance: [CONTRIBUTING](https://github.com/a11yhood/community/blob/main/CONTRIBUTING.md).

Accessibility triage is owned by the **CREATE** team at the University of Washington (create-contact@uw.edu).
