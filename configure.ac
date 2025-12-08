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
m4_define([CURRENT_VERSION], [1.8dev])
AC_INIT(pm_extra_tools, [CURRENT_VERSION])
AM_INIT_AUTOMAKE

PM_PCSGEN_VER=CURRENT_VERSION
AC_SUBST(PM_PCSGEN_VER)

# Checks for programs.
AC_PROG_LN_S

# Checks for libraries.

# Checks for header files.

# Checks for typedefs, structures, and compiler characteristics.

# Checks for library functions.

AC_SUBST([current_rhel],
         m4_esyscmd([
             cat /etc/redhat-release | sed -e 's/.*\s\([0-9]\+\)\..*/\1/'
         ]))

RSCS_PATH="${srcdir}/resources"
case $current_rhel in
    10)
        PGSQL_RA="$RSCS_PATH/pgsql.rhel10"
        HULFT_RA="$RSCS_PATH/hulft.rhel10"
        ;;
    9)
        PGSQL_RA="$RSCS_PATH/pgsql.rhel9"
        HULFT_RA="$RSCS_PATH/hulft.rhel9"
        ;;
    8)
        PGSQL_RA="$RSCS_PATH/pgsql.rhel8"
        HULFT_RA="$RSCS_PATH/hulft.rhel8"
        ;;
    *)  AC_MSG_ERROR([Unsupported RHEL version: $current_rhel]) ;;
esac

AC_CONFIG_COMMANDS([resources_setup], [
        rm -rf resources/pgsql
        cp "$pgsql_ra" resources/pgsql
        #rm -rf resources/hulft
        #cp "$hulft_ra" resources/hulft
    ], [
        pgsql_ra=$PGSQL_RA
        hulft_ra=$HULFT_RA
    ])

AC_CONFIG_FILES([Makefile
                 pm_extra_tools.spec
                 pm_pcsgen/Makefile
                 pm_pcsgen/pm_pcsgen.py
                 resources/Makefile])
AC_OUTPUT
