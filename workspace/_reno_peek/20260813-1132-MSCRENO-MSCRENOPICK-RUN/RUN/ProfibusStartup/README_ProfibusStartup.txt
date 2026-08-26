
Profibus Card Start-Up Software
==============================================================

The ProfibusStartup program loads configuration files to a Profibus Card.
Run this program before starting FortnaPlus when a new or changed Profibus
configuration is needed.


This program may be used with these options:

 * Status  -- Check the status of the Profibus card(s).

 * Reset   -- Initialize the card(s).

 * Boot    -- Load the pfb3.ss3 Profibus personality module.

 * LoadBSS -- Load the application-specific PciProfibus.bss configuration
              information.



Required files:

 ProfibusStartup -- The program.

 pfb3.ss3 -- The Profibus personality module, provided by
             SST / Woodhead Software (the manufacturer).  ProfibusStartup
			 will always look for this file when using the Boot option.

 PciProfibus.bss -- The application-specific configuration file, describing
                    the configuration of the I/O racks which this card will
					control.  This file is created for each card by the
					Fortna Controls Engineering group using another software
					package.  It is best to keep a copy of this file with
					a name that describes the specific job, node, and card
					for which it is intended, and copy it to the name
					PciProfibus.bss as needed.  ProfibusStartup will always
					look for the name PciProfibus.bss when using the
					LoadBSS option.

Place a copy of these files in the FortnaPlus RUN directory.  ProfibusStartup
looks for the .ss3 and .bss files in the current directory when the program
is run.

The application-specific BSS file MUST be copied to the file name 
"PciProfibus.bss" when using the LoadBSS option.


Run the command without options to see a help message:

 ./ProfibusStartup 


