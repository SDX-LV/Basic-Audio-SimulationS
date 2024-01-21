import subprocess   # script for Python 3
import os

#  "convert_mesh_unv_to_elmer.py" executable script automatically converts ".unv" mesh to Elmer FEM "mesh." format.
#   it reads .unv file named as specified in "Mesh_Filename_To_Convert" (usually 'FEMMesh' .unv).

#                               HOW TO USE:
#
#   1- This "convert_mesh_unv_to_elmer.py" file needs to be right next to the "FEMMesh.unv" to convert.
#   2- Windows only: It is recommended have Elmer added to PATH (an option during Elmer installation).
#           Otherwise, it is necessary to enter full path to the ElmerGrid.exe as a "root_Elmer" variable.
#   3- make sure you have Python 3.7 or newer to run this script.  & use "pip install psutil" to add required package.
#   4- "run" this "convert_mesh_unv_to_elmer.py" file with Python 3.  DONE
#           - output "FEMMesh" folder will contain all Elmer mesh related files.
#           - Bonus_VTU_output: "FEMMesh.vtu" file for opening and slicing in ParaView.
#   5- DONE
#
#   made for Python 3.7+                            see license details at the end of the script.
#       v1.00    2024-01-13     First version. Tested on Windows 11. (by Sergejs D.)
#

Mesh_Filename_To_Convert = 'FEMMesh'  # without file type extension.
root_Elmer = ''   # keep empty string if Elmer is added to PATH. Otherwise, provide full path to ..\bin\!
Bonus_VTU_output = False    # set to True  if you want


# convert ".unv" mesh to Elmer FEM "mesh." format
subprocess.call(os.path.join(root_Elmer, 'ElmerGrid 8 2 ' + Mesh_Filename_To_Convert + ' -autoclean'))


if Bonus_VTU_output:
    # convert .unv to .vtk for viewing mesh in ParaView (fault-tracing)
    subprocess.call(os.path.join(root_Elmer, 'ElmerGrid 8 5 ' + Mesh_Filename_To_Convert + ' -autoclean'))


# hold Windows command-line window open:
print('\n-------READY - (see output in the new "' + Mesh_Filename_To_Convert + '" folder) ---------------------------')
input('Hit >>> ENTER <<< to EXIT   ')


# Made for Elmer FEM   https://github.com/elmercsc/elmerfem
# licensed under the MIT license
