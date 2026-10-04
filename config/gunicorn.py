"""Never log query strings, Referer headers, or email access tokens."""

access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s'
