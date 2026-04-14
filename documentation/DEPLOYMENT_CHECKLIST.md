# Deployment Implementation Checklist

This document tracks the deployment plan implementation progress.

## ✅ Completed (This Session)

### Documentation Created

- [x] **ENVIRONMENT_QUICK_REFERENCE.md** - Quick reference guide
  - Test vs production comparison table
  - Common commands
  - Configuration file reference
  - Troubleshooting tips
  - Security reminders

- [x] **backend/.env.example** - Production configuration template
  - Comprehensive variable documentation
  - Setup checklist
  - Security warnings

### Scripts Created

- [x] **start-prod.sh** - Production startup script
  - Health checks for Supabase connection
  - Automatic supported sources seeding
  - Clear warnings about production mode
  - Executable permissions set

- [x] **stop-prod.sh** - Production shutdown script
  - Clean server shutdown
  - Helpful next-step reminders
  - Executable permissions set

## 📋 Stage 2: Cloud Deployment (Future)


### When You're Ready for Cloud

- [ ] Setup docker container
- [ ] Configure environment variables in hosting platform
- [ ] Update OAuth redirect URIs to production domain
- [ ] Update CORS origins in backend config
- [ ] Deploy backend to chosen platform
- [ ] Test production deployment
- [ ] Set up monitoring (Sentry, LogRocket, etc.)
- [ ] Set up alerts
- [ ] Document rollback procedures
- [ ] Create incident response plan

See [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) Stage 2 for detailed checklist.

## 🔍 Verification Checklist

After completing Stage 1 setup, verify:

### Backend

- [ ] API health endpoint responds: `curl http://localhost:8000/health`
- [ ] API docs accessible: http://localhost:8000/docs
- [ ] Supported sources endpoint returns data: `curl http://localhost:8000/api/sources/supported`
- [ ] Backend logs show no errors: `tail -f backend.log`

### Database

- [ ] Supabase dashboard accessible
- [ ] All tables created (users, products, ratings, reviews, discussions, etc.)
- [ ] RLS policies enabled
- [ ] Test data visible in Table Editor

### Authentication

- [ ] GitHub OAuth redirects correctly
- [ ] User created in Supabase after login
- [ ] JWT token stored in browser
- [ ] User session persists after refresh

### Data Operations

- [ ] Can create products
- [ ] Can rate products
- [ ] Can write reviews
- [ ] Can post discussions
- [ ] Can create collections
- [ ] Data persists in Supabase
- [ ] Data survives server restart

## 🐛 Troubleshooting

If any checklist item fails, see:

1. **DEPLOYMENT_PLAN.md** → Troubleshooting section
2. **ENVIRONMENT_QUICK_REFERENCE.md** → Troubleshooting section
3. **Backend logs**: `tail -f backend.log`
5. **Supabase logs**: Dashboard → Logs → Postgres Logs

Common issues and solutions documented in [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md).

## 📝 Notes

### Important Reminders

- **Security**: Never commit `.env` or `.env.local` files
- **Backups**: Supabase auto-backs up daily (check your plan)
- **Monitoring**: Check Supabase dashboard regularly for usage
- **Costs**: Monitor Supabase usage to avoid unexpected charges
- **Testing**: Always test in local production before cloud deploy

### Test vs Production

| Aspect | Test | Production |
|--------|------|-----------|
| Command | `./start-dev.sh` | `./start-prod.sh` |
| Database | Supabase test project | Supabase production project |
| Data | Can reset | Permanent |
| OAuth | Mock | Real GitHub |
| Use for | Development | Pre-cloud validation |

### Environment Files

**Tracked in Git** ✅:
- `.env.test`
- `.env.test.example`
- `.env.example`

**NOT Tracked** ❌ (in .gitignore):
- `.env` ← Create this for production

## 🎯 Success Criteria

Stage 1 is complete when:

- [x] Documentation created
- [x] Scripts created and tested
- [ ] Supabase project set up
- [ ] Environment files configured
- [ ] `./start-prod.sh` runs without errors
- [ ] Can create and persist data in Supabase
- [ ] Data survives server restarts
- [ ] All verification checklist items pass

## 📅 Timeline Estimate

- **Supabase setup**: 15-20 minutes
- **Configuration**: 10 minutes
- **Testing**: 15-20 minutes
- **Total**: ~45-60 minutes for first-time setup

## 🔄 Maintenance

### Regular Tasks

- **Weekly**: Check Supabase usage dashboard
- **Monthly**: Review Supabase logs for errors
- **Quarterly**: Rotate SECRET_KEY
- **As needed**: Update OAuth credentials

### Before Each Deployment

1. Run test suite: `pixi run test`
2. Test in local production: `./start-prod.sh`
3. Verify all features work
4. Check Supabase logs for errors
5. Review security best practices

## 📚 Related Documentation

- [DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md) - Full deployment guide
- [ENVIRONMENT_QUICK_REFERENCE.md](ENVIRONMENT_QUICK_REFERENCE.md) - Quick reference
- [LOCAL_TESTING.md](LOCAL_TESTING.md) - Test environment guide
- [QA_TESTING_GAPS.md](QA_TESTING_GAPS.md) - Manual QA checklist
- [SECURITY_BEST_PRACTICES.md](SECURITY_BEST_PRACTICES.md) - Security guidelines
