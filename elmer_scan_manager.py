import os
import shutil
import time
import argparse
import psutil  # pip install psutil
import subprocess

#       ---  "psutil" is required !  https://github.com/giampaolo/psutil/blob/master/INSTALL.rst  ---

#  "elmer_scan_manager.py" executable script/function automatically runs one or multiple Elmer FEM Scanning simulation
#  projects while maximizing computer resource utilization (max RAM, max CPU without overloading).
#  It automatically detects interrupted/incomplete simulations and therefore ElmerScanManager
#  simulation can be interrupted and started again without any user input or major loss of progress.
#
#                               HOW TO USE:             ( + you can call it as Python function from code)
#
#   1- This "elmer_scan_manager.py" file needs to be in a project folder OR one level above (to run multiple projects).
#       Elmer Scanning audio Project folder is created by MODIFYING the working example project from GitHub:
#           1- modify "Scanning_case.sif" with your boundary conditions just like any other Elmer .sif file.
#           2- check/generate "Scanning_FREQUNCIES.txt" file to define which frequencies you want to scan.
#           3- make sure that "mesh.elements" file of your geometry mesh is in the same project folder.
#   2- Windows only: It is recommended have Elmer added to PATH (an option during Elmer installation).
#           Otherwise, it is necessary to enter full path to the ElmerSolver.exe as a "root_elmer" variable.
#   3- make sure you have Python 3.7 or newer to run this script.  & use "pip install psutil" to add required package.
#   4- "run" this "elmer_scan_manager.py" file with Python 3.
#       By default, this script automatically runs projects next to the script BUT you can specify custom "start_path".
#   5- The script will manage all simulations and print out the progress until it is finished.
#       Printouts of each simulation step are saved in _log.txt files next to results (useful if something goes wrong).
#   6- It is highly recommended to check _log.txt files next to results the first completed instances to detect any
#       simulation issues mentioned in the Elmer printouts before letting the simulation continue till the end.
#   7- DONE, Use ParaView to view results ==> there should be example tutorial available on the same GitHub page.
#
# Extra tips:
#   1- It is not recommended to run multiple elmer_scan_manager.py scripts on the same computer (but it would work)
#   2- avoid folder names with spaces. Code is not tested for that.
#   3- To re-run any instance, just delete its "case_frequency_ .csv" file. That will tell elmer_scan_manager.py to
#           re-simulate that frequency step (in case there was a problem).
#   + It is recommended to re-launch ElmerScanManager after the simulation is finished. This way it will quickly
#       re-check the status and either confirm 100% ready or attempt to re-launch some instances that did not complete.
#
#
#   made for Python 3.7+                            see license details at the end of the script.
#       v1.00    2024-01-12     First version based on "NumCalcManager.py" v3.11 Tested on Windows 11. (by Sergejs D.)
#    https://sourceforge.net/p/mesh2hrtf-tools/code/ci/master/tree/utilities/legacy%20numcalc_manager/NumCalcManager.py
#       v1.10    2024-01-13     Changed into function/script format based on "plot_sofa_hrtf.py" v1.03 (by S. D.)
#    https://sourceforge.net/p/mesh2hrtf-tools/code/ci/master/tree/convert_n_analyse_HRTF/plot_sofa_hrtf.py
#       v1.11    2024-01-20     Lots of small fixes - CPU & RAM usage limiter needs redesign! (by S. D.)
version = 'v1.11'  # <<<  for printouts.


#
# The logic is:
#   ElmerScanManager checks RAM usage and launches more than 1 ElmerSolver instance IF it detects enough free RAM in the
#   system. It keeps launching new instances as resources free up. In addition, it tries to not overload the CPU
#   in case there is more than enough RAM. (all of this resource monitoring works reasonably well). To have full
#   control over RAM usage ElmerScanManager runs ElmerSolver instances with a single frequency step at a time.
#

# ToDo: future improvement ideas
#   - add start_path input to the script (so-far start_path can only be changed by editing the script itself)
#   - add nice printout for total processing time.
#   - Long-Term - try to run some low frequency instances in parallel with high-frequency instances to better utilize
#       RAM in the beginning of the simulation project (this could be tricky and require new RAM monitoring code).
#

# to see all options run   "python elmer_scan_manager.py --help"
def create_cli():
    # 1 parse command line input ----------------------------------------------------

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        "--start_path", default='False', type=str,
        help=("Optional Search directory or full path to Elmer Scan project folder (where Scanning_case.sif file is). "
              "If start_path='False' - projects are searched right next to this script OR in sub-folders. "
              "If start_path=r'path' - projects are searched inside given folder OR its sub-folders (multiple projects)"
              " Note, use raw strings r\"...\" raw strings without \"\\\" in the end!."))
    #  example start_path:  default= r"D:\git_D\Basic-Audio-SimulationS"  # (use r"..." raw strings without end "\"
    #  default start_path:  default= 'False'                              # auto-detection
    parser.add_argument(
        "--auto_set_max_instances", default='True', choices=('True', 'False'), type=str,
        help=("Feature to autodetect how many solver instances can be run concurrently to not overload CPU."
              " NOTE - does not work very reliably! Usually is fine, but you may prefer manual max_instances."))
    parser.add_argument(
        "--max_instances", default='8', type=int,
        help='Default instance limit is used in case auto_set_max_instances=False.')
    parser.add_argument(
        "--root_elmer", default='', type=str,
        help=("Optional full path to  Elmer bin folder in case ElmerSolver can not be found by filename alone. "
              "The default empty string works great if Elmer was added to PATH during installation."))
    parser.add_argument(
        "--sec_to_initialize", default='7', type=float,
        help='delay in seconds during which new ElmerSolver instance should initialize its full RAM usage. ')
    parser.add_argument(
        "--ram_safety_factor", default='0.95', type=float,
        help=("Extra instances are launched when free RAM is greater than "
              "RAM consumption of the biggest ElmerSolver instance * ram_safety_factor."))
    parser.add_argument(
        "--max_cpu_load_percent", default='80', type=float,
        help=("target % for how much CPU can be used by ElmerSolver, assuming that RAM allows for so many "
              "instances. Consider to lower limit to keep computer responsive for mutitasking!"
              " Note: the actual CPU usage can be higher - not a precise algorithm!."))
    parser.add_argument(
        "--cleanup_after_finish", default='True', choices=('True', 'False'), type=str,
        help="Delete not-useful files generated during simulation after completion.")

    args = vars(parser.parse_args())
    return args


# END create_cli


def main(start_path='False', auto_set_max_instances=True, max_instances=8, root_elmer='', sec_to_initialize=7,
         ram_safety_factor=0.95, max_cpu_load_percent=80, cleanup_after_finish=True):
    # 2 initialization --------------------------------------------------------------

    # hard-coded filenames:
    main_frequencies_to_simulate = 'Scanning_FREQUNCIES.txt'  # each row contains one frequency value in [Hz]
    main_solver_input = 'Scanning_case.sif'  # used as the base for generating startup instructions into "generated_sif"
    generated_sif = 'case.sif'
    start_info_file = 'ELMERSOLVER_STARTINFO'
    post_file = 'case_t'
    freq_file = 'case_frequency_'
    freq_file_ext = '.csv'
    headers_to_delete = '.csv.names'
    #  not used:     post_file_ext = '.vtu'
    required_input_files = [main_solver_input, main_frequencies_to_simulate, 'mesh.elements']
    if os.name == 'nt':  # Windows detected
        elmersolver_executable = "ElmerSolver.exe"
    else:  # elif os.name == 'posix': # Linux or Mac detected
        elmersolver_executable = "ElmerSolver"

    os.system("")  # trick to get colored print-outs   https://stackoverflow.com/a/54955094
    text_color_red = '\033[31m'
    text_color_cyan = '\033[36m'
    text_color_reset = '\033[0m'
    #  not used:     text_color_green = '\033[32m'

    #  not used:     start_time = time.localtime()  # init (can be overwritten later!)

    working_dir = os.path.dirname(os.path.realpath(__file__))  # similar to "getcwd()"

    print('--- "' + os.path.basename(__file__) + '" v' + version + ' started with start_path = "' + start_path + '"')
    print('   input arg:  "start_path" = ' + str(start_path))
    print('   input arg:  "auto_set_max_instances" = ' + str(auto_set_max_instances))
    print('   input arg:  "max_instances" = ' + str(max_instances))
    print('   input arg:  "root_elmer" = ' + str(root_elmer))
    print('   input arg:  "ram_safety_factor" = ' + str(ram_safety_factor))
    print('   input arg:  "max_cpu_load_percent" = ' + str(max_cpu_load_percent) + '%')
    print('   input arg:  "cleanup_after_finish" = ' + str(cleanup_after_finish))

    if start_path == 'False':
        print('   (searching for simulation projects next to "' + os.path.basename(__file__) + '")')
        start_path = working_dir

    # Detect what the start_path is pointing to:
    if os.path.isfile(os.path.join(start_path, main_solver_input)):  # - is it Project folder?
        all_projects = [start_path]  # correct project folder
    else:  # - is it a folder with multiple projects?
        all_projects = []  # list of project folders to execute
        for subdir in os.listdir(start_path):
            if os.path.isfile(os.path.join(start_path, subdir, main_solver_input)):  # - is it Project folder?
                # Check that all necessary project files are present:
                all_good = True  # re-init
                for calc_file in required_input_files:
                    if not os.path.isfile(os.path.join(start_path, subdir, calc_file)):
                        all_good = False
                if all_good:
                    all_projects.append(os.path.join(start_path, subdir))  # generate list of project folders to execute
                else:
                    print("NOTE - incomplete project folder skipped: " +
                          os.path.join(start_path, subdir))

    if len(all_projects) == 0:  # not good
        print(text_color_red + 'ERROR - start_path = "' + start_path + '" does not contain any valid projects to run')
        print(text_color_red + ' Please make sure that "start_path" is valid')
        input(text_color_red + "  -press Enter- to exit ElmerScanManager.")
        raise Exception("not ok to continue")

    # Test if ElmerSolver executable exists:
    full_path_info = shutil.which(elmersolver_executable)
    if full_path_info is None:
        print(text_color_red + 'ERROR - ElmerSolver was not found, check that:')
        print(text_color_red + ' 1- Elmer FEM solver is installed')
        print(text_color_red + ' 2- on Windows it needs to be added to PATH during installation OR')
        print(
            text_color_red + ' 3- You may need to provide full path to .exe file in "elmersolver_executable" variable')
        input(text_color_red + "  -press Enter- to exit ElmerScanManager.")
        raise Exception("not ok to continue")

    # Check all projects that may need to be executed:
    if len(all_projects) > 1:
        projects_to_run = []  # init boolean
        for proj in range(len(all_projects)):
            all_steps, steps_to_run, freq_of_steps_to_run = \
                check_project(all_projects[proj], required_input_files, main_frequencies_to_simulate, freq_file,
                              freq_file_ext, text_color_red)
            if len(steps_to_run) > 0:
                projects_to_run.append(all_projects[proj])  # mark to run this project
                print('Project "' + os.path.basename(all_projects[proj]) + '" has ' + str(len(steps_to_run)) +
                      ' out of ' + str(len(all_steps)) + ' instances to run')
            else:
                print('Project "' + os.path.basename(all_projects[proj]) + '" is already complete')
    else:
        projects_to_run = all_projects
        # #    if not all(Project_to_run):  # all projects are finished  (no problem)
    del all_projects  # just to avoid bugs: removing variables that are no longer relevant

    # 3 Loop to process all projects  --------------------------------------------------------------    
    for proj in range(len(projects_to_run)):

        os.chdir(projects_to_run[proj])  # change to the project directory (for ElmerSolver to find input files)

        # Check how many instances are in this Project:
        all_steps, steps_to_run, freq_of_steps_to_run = \
            check_project(projects_to_run[proj], required_input_files, main_frequencies_to_simulate, freq_file,
                          freq_file_ext, text_color_red)
        total_nr_to_run = len(steps_to_run)

        # Status printouts:
        if len(projects_to_run) > 1:
            print(text_color_reset + " ")
            print(text_color_reset + " ")
            print(text_color_cyan + " Started Project", str(proj + 1), " out of ", str(len(projects_to_run)),
                  "detected projects to run")
            print(text_color_reset + " ")
            print(text_color_reset + " ")
        print("--- ", str(len(all_steps)), "frequency steps defined in this Elmer Scanning simulation project")
        if total_nr_to_run == 0:
            print("--- This Simulation project is already Complete. ---")
        else:
            print("--- ", str(total_nr_to_run),
                  "steps are not yet completed. (Starting from the max frequency)")

        # Sort list to run the largest frequencies that consume the most RAM first
        sorting_list = sorted(zip(freq_of_steps_to_run, steps_to_run), reverse=True)
        steps_to_run = [x for y, x in sorting_list]  # sort "steps_to_run" according to decreasing frequency
        freq_of_steps_to_run = [y for y, x in sorting_list]  # update Matched list to correspond to "steps_to_run"
        del sorting_list  # remove no longer needed variables

        start_time = time.localtime()
        print(time.strftime("%d %b - %H:%M:%S", start_time))

        # read in simulation parameters once:
        with open(os.path.join(projects_to_run[proj], main_solver_input), 'r') as contents:
            main_case_sif = contents.read()

        # make sure there is a start_info_file (generate it if needed)
        if not os.path.isfile(os.path.join(projects_to_run[proj], start_info_file)):
            with open(os.path.join(projects_to_run[proj], start_info_file), "w", encoding="utf8",
                      newline="\n") as text_file:
                text_file.write(generated_sif + "\n1\n")  # first & second lines

        # 4 main loop for each step/instance  --------------------------------------------------------------        
        for sim_step in range(0, total_nr_to_run):
            step = steps_to_run[sim_step]
            print("- ", str(sim_step + 1), "/", str(total_nr_to_run), " preparing >>>",
                  str(freq_of_steps_to_run[sim_step]),
                  "Hz <<< instance at step", str(step))

            # double check (roughly) that this instance does not have output
            path_to_check = os.path.join(projects_to_run[proj], freq_file + str(step) + freq_file_ext)
            if os.path.isfile(path_to_check):
                print(text_color_cyan, "step with output file ", freq_file + str(step) + freq_file_ext,
                      "--- already has output data! Skipping")
                print(text_color_reset + " ")
                continue  # jump over this instance

            # Check the RAM & run instance if feasible
            ram_info = psutil.virtual_memory()
            print(str(round((ram_info.available / 1073741824), 2)), "GB free", "    ---    RAM memory used:",
                  str(ram_info.percent), "%     [", time.strftime("%d %b - %H:%M:%S", time.localtime()), "]")

            # Run this once - normally before launching the 2nd instance IF "auto_set_max_instances == True"
            if sim_step > 0 and auto_set_max_instances:  # use this to autodetect how many instances should be executed.
                # noinspection PyBroadException
                try:
                    # it is better to get fresh pid (hopefully at least one ElmerSolver process is still running)
                    pid_name_bytes = [(p.pid, p.info['name'], p.info['memory_info'].rss) for p in
                                      psutil.process_iter(['name', 'memory_info']) if
                                      p.info['name'] == elmersolver_executable]
                    prc_info = psutil.Process(pid_name_bytes[0][0])
                    instance_cpu_usage_now = prc_info.cpu_percent(interval=1.0) / psutil.cpu_count()

                    # calculate optimal maximum number of ElmerSolver processes for this system:
                    max_instances = round(max_cpu_load_percent / instance_cpu_usage_now)
                    print("One instance loads CPU to", str(round(instance_cpu_usage_now, 1)),
                          "% on this machine, therefore",
                          "max_instances is now automatically set =", str(max_instances))
                    auto_set_max_instances = False  # mark that max instances does not need to be checked again.
                except BaseException:
                    print(
                        "!!! Failed to auto_set_max_instances - this can happen if ElmerSolver process finished ",
                        "very fast - you could try to lower your ""sec_to_initialize"" setting.")

            #  Main checks before launching the next instance (to avoid system resource overload)
            wait_for_resources = True  # re-init
            if sim_step == 0:
                wait_for_resources = False  # always run 1st instance.

            while wait_for_resources:
                # Find all ElmerSolver Processes
                pid_name_bytes = [(p.pid, p.info['name'], p.info['memory_info'].rss) for p in
                                  psutil.process_iter(['name', 'memory_info']) if
                                  p.info['name'] == elmersolver_executable]
                # # FOR DEBUGGING --- Find Processes consuming more than 250MB of memory:
                # # pid_name_bytes = [(p.pid, p.info['name'], p.info['memory_info'].rss) for p in psutil.process_iter(
                #       ['name', 'memory_info']) if p.info['memory_info'].rss > 250 * 1048576]

                if len(pid_name_bytes) == 0:  # if no ElmerSolver processes are running, so Go start one instance.
                    break

                elif len(pid_name_bytes) < max_instances:  # if the max number of instances to launch is not exceeded

                    # find out how much RAM consumes the biggest ElmerSolver Instance
                    max_elmersolver_ram = pid_name_bytes[0][2]  # init
                    if len(pid_name_bytes) > 1:  # if more than one process
                        for prcNr in range(1, len(pid_name_bytes)):
                            if pid_name_bytes[prcNr][2] > max_elmersolver_ram:
                                # finding ElmerSolver process that consumes the most RAM
                                max_elmersolver_ram = pid_name_bytes[prcNr][2]

                    # check if we can run more:  Is free RAM is greater than
                    #                       RAM consumption of the biggest ElmerSolver instance * ram_safety_factor .
                    ram_info = psutil.virtual_memory()
                    # CPU load - still not the same CPU load estimate compared to Windows TaskManager!
                    total_cpu_load = psutil.cpu_percent(interval=0.5, percpu=False)  # takes 0.5 seconds!!!
                    if ((ram_info.available > max_elmersolver_ram * ram_safety_factor) &
                            (total_cpu_load < max_cpu_load_percent)):
                        print("   enough RAM to run one more:     ", str(round((ram_info.available / 1073741824), 1)),
                              "GB free", "     [", time.strftime("%d %b - %H:%M:%S", time.localtime()), "]")
                        break

                    else:
                        if total_cpu_load > max_cpu_load_percent:  # CPU limitation
                            print("   Waiting for less load on CPU:     ", str(total_cpu_load),
                                  "% CPU load    (", str(max_cpu_load_percent), "% allowed)     [",
                                  time.strftime("%d %b - %H:%M:%S", time.localtime()), "]")
                        else:   # RAM limitation
                            print("   Waiting for more free RAM:     ",
                                  str(round((ram_info.available / 1073741824), 1)), "GB free    (",
                                  str(round((max_elmersolver_ram * ram_safety_factor / 1073741824), 1)), "GB needed)",
                                  "     [", time.strftime("%d %b - %H:%M:%S", time.localtime()), "]")

                        if len(pid_name_bytes) == 1:  # only one process
                            # extra delay before trying the while loop again for very large processes
                            time.sleep(4 * sec_to_initialize)

                else:
                    print("   No more instances allowed - waiting for 1 out of", str(max_instances),
                          "instances to finish")

                # delay before trying the while loop again
                time.sleep(sec_to_initialize)

            # END of wait_for_resources while loop

            # START one more instance
            print("- ", str(sim_step + 1), "/", str(total_nr_to_run), " STARTING instance from:",
                  projects_to_run[proj], ">>>    step", str(step))

            # (over) Write the simulation .sif parameters for this instance:
            two_lines = "$npart = " + str(step) + "\n$f = " + str(freq_of_steps_to_run[sim_step]) + " 		! Hz \n\n"
            with open(os.path.join(projects_to_run[proj], generated_sif), 'w') as contents:
                contents.write(two_lines + main_case_sif)  # overwrite case.sif with instructions for this step

            if os.name == 'nt':  # Windows detected
                log_file_handle = open(post_file + str(step) + "_log.txt", "w")  # create a log file for all print-outs
                # run ElmerSolver & route all printouts to a log file
                subprocess.Popen(os.path.join(root_elmer, elmersolver_executable), stdout=log_file_handle)

            else:  # elif os.name == 'posix': # Linux or Mac detected
                # run ElmerSolver & route all printouts to a log file
                subprocess.Popen(elmersolver_executable + " >" + post_file + str(step) + "_log.txt", shell=True)

            # optimize waiting time (important if available RAM >>> than needed RAM)
            if sim_step > 0:  # on the not-first loop
                # noinspection PyUnboundLocalVariable
                if ram_info.available > max_elmersolver_ram * 3:  # if there is RAM for over (3-1) instances
                    wait_time = 0.5  # practically do not wait if we have lots of RAM
                elif ram_info.available > max_elmersolver_ram * 2:  # if there is 2x more RAM than necessary, speed up
                    wait_time = sec_to_initialize / 2  # practically do not wait if we have lots of RAM
                else:
                    wait_time = sec_to_initialize  # wait properly to assess how muchRAM will be left
                print("   ... waiting", str(wait_time), "s for current instance to initialize RAM")

            else:  # effectively: NC_ins == 0:
                wait_time = sec_to_initialize  # always let the 1st instance to initialize to get worst-case RAM use
                print("   ... waiting", str(sec_to_initialize), "s for the 1st instance to initialize RAM")

            # Wait for current instance to initialize before attempting to start the next instance
            time.sleep(wait_time)

            # Check if all ElmerSolver processes crashed:    Find all ElmerSolver Processes
            pid_name_bytes = [(p.pid, p.info['name'], p.info['memory_info'].rss) for p in
                              psutil.process_iter(['name', 'memory_info']) if p.info['name'] == elmersolver_executable]
            if len(pid_name_bytes) == 0:
                print(text_color_red +
                      "ERROR - ElmerSolver processes are NOT running! likely the last launched instance crashed.")
                print(text_color_red + " Read " + post_file + str(step) + "_log.txt file for more details.")
                input(text_color_red + "  -press Enter- to exit ElmerScanManager.")
                raise Exception("not ok to continue")

        #  END of the main project loop.

        print("waiting for last processes to finish (in this project)")
        while True:
            # Find all ElmerSolver Processes
            pid_name_bytes = [(p.pid, p.info['name'], p.info['memory_info'].rss) for p in
                              psutil.process_iter(['name', 'memory_info']) if p.info['name'] == elmersolver_executable]

            if len(pid_name_bytes) == 0:
                break  # no ElmerSolver processes are running, so Finish.

            print("... waiting", str(2 * sec_to_initialize), "s for the last ElmerSolver instances to finish")
            time.sleep(2 * sec_to_initialize)

        # Clean-up
        if cleanup_after_finish:  # cleanup_after_finish == TRUE
            print("Cleaning away not-needed and confusing files after completion because cleanup_after_finish == True")
            if os.path.isfile(os.path.join(projects_to_run[proj], generated_sif)):
                os.remove(os.path.join(projects_to_run[proj], generated_sif))  # delete case.sif to not confuse

            for a_file in os.listdir(projects_to_run[proj]):
                if a_file.startswith(freq_file) & a_file.endswith(headers_to_delete):
                    os.remove(os.path.join(projects_to_run[proj], a_file))  # delete all header files for frequency

    #  END of all_projects loop.

    os.chdir(working_dir)  # change back to initial directory (wrapping up)

    # finalize
    # # print("Total processing time with ElmerScanManager:   ", time.strftime("%H:%M:%S", time.time() - start_time))
    print("ElmerScan project is COMPLETE.   ", time.strftime("%d %b - %H:%M:%S", time.localtime()))

# END main


# function to find all unfinished instances in a given project folder + other problems & details
def check_project(project, required_input_files, main_freq_to_simulate, freq_file, freq_f_ext, text_color_red):
    frequencies = []  # init  Values of frequency for each scanning step
    all_step_nr = []  # init  Numbers of each step. (it can be useful to explicitly simulate only specific numbers)
    step_counter: int = 0  # init  number of simulation steps (same as "len(frequencies)"  )

    # Check that all necessary project files are present:
    for calc_file in required_input_files:
        if not os.path.isfile(os.path.join(project, calc_file)):
            print(text_color_red + "ERROR - Required project file " + calc_file + " is not found in folder:")
            print(text_color_red + "         " + project)
            input(text_color_red + "  -press Enter- to exit ElmerScanManager.")
            raise Exception("not ok to continue")

    # parse Main_frequencies_to_simulate .txt to get info about frequencies and instances
    # open file, iterate over lines, append values (accepts . and , separated decimals but no thousand separators)
    with open(os.path.join(project, main_freq_to_simulate), 'r') as f:
        for line in f.readlines():
            _line = line.split()
            if len(_line) == 1:  # single column with frequencies only
                frequencies.append(float(_line[0].replace(',', '.')))
                step_counter += 1
                all_step_nr.append(step_counter)
            elif len(_line) == 2:  # double column with defined step number and frequencies
                frequencies.append(float(_line[1].replace(',', '.')))
                step_counter += 1
                all_step_nr.append(int(_line[0]))
            elif not len(_line) == 0:  # empty lines are OK - just skip
                raise Exception("incompatible " + main_freq_to_simulate + " file!")

    # quick sanity check of input for duplicates:
    if len(set(all_step_nr)) != len(all_step_nr):
        print(text_color_red + "ERROR - " + main_freq_to_simulate + " file contains duplicate step numbers!")
        print(text_color_red + "         in project " + project)
        input(text_color_red + "  -press Enter- to exit ElmerScanManager.")
        raise Exception("not ok to continue")

    # check already completed simulation steps:
    steps_to_run = all_step_nr.copy()  # init list of steps        that need to be simulated
    freq_of_steps_to_run = frequencies.copy()  # init list of frequencies  that need to be simulated
    for b_file in os.listdir(project):
        # use the Frequency text file as proof of completed simulation because it is written After the main result .vtu
        # file & is very small: likelihood that simulation is interrupted while this file is being written is very low.
        if b_file.startswith(freq_file) & b_file.endswith(freq_f_ext):
            this_all_step_nr = int(b_file[len(freq_file): -len(freq_f_ext)])
            index_to_drop = steps_to_run.index(this_all_step_nr)
            # Drop this scanning simulation step of the to-do list
            del steps_to_run[index_to_drop]
            del freq_of_steps_to_run[index_to_drop]

    return all_step_nr, steps_to_run, freq_of_steps_to_run


# END check_project


if __name__ == '__main__':
    main(**create_cli())

    print('\n-------READY--------------------------------------------------')
    input('Hit >>> ENTER <<< to EXIT   ')
# END __name__


# Authors:      Sergejs Dombrovskis
#            Made for Elmer FEM   https://github.com/elmercsc/elmerfem
#
# licensed under the MIT license
#
