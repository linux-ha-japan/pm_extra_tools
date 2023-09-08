#                                               -*- Autoconf -*-
# Process this file with autoconf to produce a configure script.

AC_PREREQ([2.69])
# TODO : In the future, when using separate versions for RHEL8 and RHEL9, please enable the following processing.
#m4_define([CURRENT_VERSION],
#          m4_esyscmd([
#                      if [ `cat /etc/redhat-release | sed -e 's/.*\s\([0-9]\)\..*/\1/'` = "9" ];then 
#			      printf "1.5"
#		      else
#			      printf "1.4"
#		      fi
#                     ]))
#
#AC_INIT(pm_extra_tools, [CURRENT_VERSION])
AC_INIT(pm_extra_tools, 1.5)
AM_INIT_AUTOMAKE

# Checks for programs.
AC_PROG_LN_S

# Checks for libraries.

# Checks for header files.

# Checks for typedefs, structures, and compiler characteristics.

# Checks for library functions.

AC_CONFIG_FILES([Makefile
                 pm_extra_tools.spec
                 pm_pcsgen/Makefile
                 resources/Makefile])
AC_OUTPUT
