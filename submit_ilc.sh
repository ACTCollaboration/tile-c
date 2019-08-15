#!/bin/bash

mpi_niagara 1 "python bin/make_ilc.py map_v1.0.0_rc_joint v1.0.0_rc deep56 d56_01,d56_02,d56_03,d56_04,d56_05,d56_06,p01,p02,p03,p04,p05,p06,p07,p08 CMB,tSZ,CMB-tSZ,CMB-CIB,tSZ-CMB,tSZ-CIB 1.6,1.6,2.4,2.4,2.4,2.4 -o " -t 80 --walltime "01:00:00"

mpi_niagara 1 "python bin/make_ilc.py map_v1.0.0_rc_joint v1.0.0_rc boss boss_01,boss_02,boss_03,boss_04,p01,p02,p03,p04,p05,p06,p07,p08 CMB,tSZ,CMB-tSZ,tSZ-CMB,tSZ-CIB,CMB-CIB 1.6,1.6,2.4,2.4,2.4,2.4 " -t 80 --walltime "01:00:00"

mpi_niagara 1 "python bin/make_ilc.py map_v1.0.0_rc_planck v1.0.0_rc deep56 p01,p02,p03,p04,p05,p06,p07,p08 CMB,tSZ,CMB-tSZ,CMB-CIB,tSZ-CMB,tSZ-CIB 7.0,7.0,10.0,10.0,10.0,10.0 -o " -t 80 --walltime "01:00:00"

mpi_niagara 1 "python bin/make_ilc.py map_v1.0.0_rc_planck v1.0.0_rc boss p01,p02,p03,p04,p05,p06,p07,p08 CMB,tSZ,CMB-tSZ,tSZ-CMB,tSZ-CIB,CMB-CIB 7.0,7.0,10.0,10.0,10.0,10.0 " -t 80 --walltime "01:00:00"

mpi_niagara 1 "python bin/make_ilc.py map_v1.0.0_rc_act v1.0.0_rc boss boss_01,boss_02,boss_03,boss_04 CMB,tSZ,CMB-tSZ,tSZ-CMB,tSZ-CIB,CMB-CIB 1.6,1.6,2.4,2.4,2.4,2.4 " -t 80 --walltime "01:00:00"

mpi_niagara 1 "python bin/make_ilc.py map_v1.0.0_rc_act v1.0.0_rc deep56 d56_01,d56_02,d56_03,d56_04,d56_05,d56_06 CMB,tSZ,CMB-tSZ,CMB-CIB,tSZ-CMB,tSZ-CIB 1.6,1.6,2.4,2.4,2.4,2.4 -o " -t 80 --walltime "01:00:00"
