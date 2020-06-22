MAINTAINERCLEANFILES = Makefile.in

SUBDIRS		= pm_pcsgen resources

TARFILE		= $(PACKAGE_NAME)-$(VERSION).tar.gz
SPEC		= $(PACKAGE_NAME).spec
EXTRA_DIST	= $(SPEC)

AUTOMAKE_OPTIONS = foreign

RPM_ROOT	= $(CURDIR)
RPMBUILDOPTS	= --define "_sourcedir $(RPM_ROOT)" \
		  --define "_specdir $(RPM_ROOT)"

$(TARFILE):
	$(MAKE) dist

srpm: clean
	rm -f $(TARFILE)
	$(MAKE) $(SPEC) $(TARFILE)
	rpmbuild $(WITH_LIST) $(RPMBUILDOPTS) --nodeps -bs --rmsource $(SPEC)

rpm: clean
	rm -f $(TARFILE)
	$(MAKE) $(SPEC) $(TARFILE)
	rpmbuild $(WITH_LIST) $(RPMBUILDOPTS) -ba --rmsource $(SPEC)
