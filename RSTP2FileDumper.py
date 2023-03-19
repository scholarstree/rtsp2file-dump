from gooey import Gooey, GooeyParser
from gooey import Events
from gooey.python_bindings import signal_support
from datetime import datetime
import ffmpeg
import subprocess
import shlex
from io import BytesIO
import signal 
import os
import time

import sys
import signal
from textwrap import dedent
import json

signal_support.install_handler() # for windows

def resource_path(relative_path):
    """
    PyInstaller creates a temporary folder at every run of executable program and unpacks resources. 
    We need to use resources from this temperory folder. Using relative path (to python script) of resources 
    will result in error.

    :param str relative_path: Path to a resource
    :return: Path of the resource in the temporary folder
    """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def rtsp_link_checker(rtsp_link):
    """ 
    1. Check for correct rtsp link format
    2. Probe the link to check if it is working
    """
    if len(rtsp_link) < 7 or rtsp_link[:7] != "rtsp://":
        raise TypeError("Enter correct RTSP link. Should start with rtsp://")
    else:
        probe_command = ['ffprobe',
                    '-v', 'quiet',
                    '-print_format', 'json',
                    '-timeout', '5000000',
                    '-show_streams', rtsp_link]
        process = subprocess.Popen(probe_command, stdout=subprocess.PIPE)
        response_json = json.loads(process.communicate()[0]) # Reading content of p0.stdout (output of FFprobe) as string
        if (process.wait() == 0): # no error
            if (len(response_json['streams']) != 0 and (response_json['streams'][0]['width'] != 0 and response_json['streams'][0]['height'] != 0)):
                return rtsp_link
            else:
                raise TypeError("RTSP link not working. No frames found.")
        else:
            raise TypeError("RTSP link not working. Connection failed.")

def savepath_checker(save_file):
    """ 
    Check for valid filepath
    """
    path_split = os.path.split(save_file)
    
    if (path_split[-1].rfind(".") == -1 or (path_split[-1].rfind(".") == len(path_split[-1])-1)): # no file extension provided
        raise TypeError("Select valid file path.")
    elif (os.path.isdir(path_split[0]) == False and path_split[0] != ''):
        raise TypeError("Select valid file path. ", path_split[0] +" is not a valid directory.")  
    else:
        return save_file

def positive_int_validator(value):
    """ 
    Supported values: positive int
    """
    if not value.isnumeric:
        raise TypeError("Select a valid vlaue.")
        return
    elif value.isdigit() and int(value) >=0:
        return value
    else:
        raise TypeError("Select a positive integer for segment length")

########################################################## Gooey App ##########################################################
@Gooey(program_name="RSTP2FileDumper", 
        show_success_modal=False, 
        default_size=(700, 680),
        use_events=[Events.VALIDATE_FORM], 
        navigation='SIDEBAR',
        dump_build_config = False,
        shutdown_signal=signal.CTRL_C_EVENT,
        show_preview_warning=False,
        show_restart_button=False, # THIS WON'T WORK (REMINDER: Don't remember why)
        image_dir=resource_path('images'),
        menu=[{
        'name': 'File',
        'items': [{
                'type': 'AboutDialog',
                'menuTitle': 'About',
                'name': 'RSTP2FileDumper',
                'description': 'Save RTSP stream to file',
                'version': '1.0',
                'copyright': '2023',
                'developer': 'scholarstree',
                'license': 'MIT'
            }]
        },{
        'name': 'Help',
        'items': [{
            'type': 'Link',
            'menuTitle': 'Documentation',
            'url': '-'
        }]
    }])

def get_args():
    parser = GooeyParser(description="v1.0")

    # Subparsers for TABBED view. Currently only 1 tab
    subparsers = parser.add_subparsers(help="commands", dest="command") 

    ################################## RSTP 2 File Dumper ##################################
    file = subparsers.add_parser("rtsp_to_file_dump", prog="RSTP 2 File Dumper")
    file_group1 = file.add_argument_group('RTSP Settings')
    file_group2 = file.add_argument_group('File Settings')

    file_group1.add_argument('-r', '--rtsp', metavar="RTSP Link",  default="rtsp://",
                        gooey_options={'full_width':True}, 
                        help="Remember username & password in the rtsp link if required") 

    
    file_group2.add_argument('-of', '--output_file', metavar="Output File",
                        widget='FileSaver', 
                        gooey_options={'wildcard':"Video File Formats mp4,mkv,avi,wmv,mov|*.mp4;*.mkv;*.avi;*wmv;*mov|""All files (*.*)|*.*",
                                        'default_dir': "./", 
                                        'full_width':True,
                                        'message': "Select output filename"}, 
                        default="rtsp2filedump.mp4",
                        help="Output filename", type=savepath_checker)
    
    file_group2.add_argument('-sg', '--segment_length', metavar="Segment Length (sec)", default=300, 
                    gooey_options={'full_width':False}, 
                    help="Save stream in segments of length (sec) | Select 0 for unlimited length", type=positive_int_validator) 
    
    file_group2.add_argument('-os', '--output_suffix', metavar="Output File Suffix", widget='CheckBox', default=True, action="store_false", help="Add unique suffix to output file to avoid accidental override to existing file")

    return parser.parse_args()

def add_unique_suffix_to_filename(path):
    now = datetime.now()
    suffix = "_" + str(now.year) + str(now.month) + str(now.day) + "_" + str(now.hour) + "_" + str(now.minute) + "_" + str(now.second) + "_" + str(int(now.microsecond/1000)) 

    path_dot_idx = path.rfind(".")
    path_split = path.split('.')

    if (len(path_split) == 1):
        return path[:path_dot_idx] + suffix + ".mp4"
    else:
        return path[:path_dot_idx] + suffix + path[path_dot_idx:]

def rtsp_to_file_dump(args):
    """
    Dumps RTSP stream 'args.rtsp' to file 'args.output_file'
    """

    if not args.output_suffix: # this is not bug. https://github.com/chriskiehl/Gooey/issues/148
        save_filename = add_unique_suffix_to_filename(args.output_file)
    else:
        save_filename = args.output_file

    dot_pos = save_filename.rfind(".")
    save_filename = save_filename[:dot_pos] + "_part%d" + save_filename[dot_pos:]
    logs_filename = save_filename[:dot_pos] + '.txt'
    print("Dumping ", args.rtsp, " to ", save_filename)

    ### 
    # VERY TRICKY to make ffmpeg work with pyinstaller
    # Unable to make output visible in app window when run from EXE. Check logs instead.
    ###


    ### Using ffmpeg-python package
    stream = ffmpeg.input(args.rtsp)
    if (args.segment_length == 0):
        stream = ffmpeg.output(stream, save_filename, fflags='nobuffer', vcodec='copy')
    else:
        stream = ffmpeg.output(stream, save_filename, fflags='nobuffer', vcodec='copy', f='segment', segment_time=args.segment_length, reset_timestamps=1) # flags='low_delay'
    stream = stream.global_args('-nostats')
    ffmpeg.run(stream)

    #### Using subprocess
    # cmd = ['ffmpeg', 
    #        '-i', args.rtsp, '-nostats',
    #        '-fflags', 'nobuffer',
    #        '-vcodec', 'copy', 
    #        '-f', 'segment',
    #        '-segment_time', args.segment_length,
    #        '-reset_timestamps', '1',
    #        '-y', save_filename]
    # with open(logs_filename, 'w') as log:
    #     process = subprocess.Popen(cmd,
    #                                 bufsize=1,
    #                                 stdin=subprocess.PIPE,
    #                                 stdout=subprocess.PIPE,
    #                                 universal_newlines=True, 
    #                                 stderr=log)
    #     stdout, stderr = process.communicate()

    #    # for line in process.stdout:
    #    #     print(line)

########################################################## Main Function ##########################################################
def main():
    try:
        args = get_args()
        rtsp_to_file_dump(args)

    except KeyboardInterrupt:
        print("Stopped dumping.")

########################################################## Run Script ##########################################################
if __name__ == '__main__':
    main()
