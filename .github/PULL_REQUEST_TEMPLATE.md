## Summary

What does this change, and why? Link the issue (e.g. `Closes #123`).

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor or cleanup
- [ ] Documentation
- [ ] Database migration
- [ ] Security-related

## Testing

- [ ] Tests added or updated
- [ ] Tests pass locally (note the command and environment, e.g. `ENV_FILE=.env.test pixi run python -m pytest`)
- [ ] If tests were not run (or only some), say which and why:

## Database and security

- [ ] No migration needed, or the migration is included and described (note whether it is applied to test and/or production)
- [ ] New or changed SQL functions: `EXECUTE` is revoked from `PUBLIC`/`anon`/`authenticated` unless intentionally public
- [ ] No secrets, keys, or tokens committed; new settings are documented in `env.example`
- [ ] Authorization is enforced server-side for new or changed endpoints
- [ ] User-controlled text is validated or escaped where it is displayed or emailed

## Accessibility

Complete this section for any change to user-facing output (API error messages, emails, generated text, documentation). Otherwise write "N/A".

- [ ] Error messages and other text are clear, in plain language, and say what to do next
- [ ] Emails and generated content have a plain-text version, descriptive subjects, and meaningful link text
- [ ] Meaning is not conveyed by color or images alone
- [ ] Documentation changes use headings, descriptive links, and text alternatives for images
- [ ] Fields the website needs for accessibility (alt text, titles, descriptions) are supported

## Notes for reviewers

Risks, trade-offs, follow-up work.
