MAINTAINERCLEANFILES	= Makefile.in

pcsgendir		= /usr/share/pm_extra_tools
pcsgen_SCRIPTS		= pm_pcsgen.py
pcsgen_DATA		= pm_pcsgen.conf pm_pcsgen_sample.xlsx
pcsgenlinkdir		= /usr/bin

CLEANFILES		= $(pcsgen_SCRIPTS)
EXTRA_DIST		= $(pcsgen_SCRIPTS) $(pcsgen_DATA)

install-exec-hook:
	test -z $(pcsgenlinkdir) || $(mkdir_p) $(DESTDIR)$(pcsgenlinkdir)
	$(LN_S) -f $(pcsgendir)/$(pcsgen_SCRIPTS) $(DESTDIR)$(pcsgenlinkdir)/pm_pcsgen

uninstall-local:
	rm -rf $(pcsgenlinkdir)/pm_pcsgen
