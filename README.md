# CallOfDutyColdWarBestPlayApp
This is a Best Play Video Trimmer for Cold War. With this app you can script the trimming of your videos.

TO Install.

download two files from here and put them in some folder on your MACOS operating system (not tested on Windows)

1. build_mac_studio.command
2. fan_cave_studio.py

Create a new folder somewhere like your Desktop, Documents, or Users root folder for example. 

Save these two files in that directory

Open a Terminal prompt (DO NOT SUDO, not required)
cd to the directory where you saved the files. Mine was in 
"cd /Users/admin/Desktop/FCSP"
then you need to change the permissions for build_mac_studio.command so that it is executable. To do this run

"chmod +x build_mac_studio.command"

Then run the build_mac_studio.command one time installer (I will post an example installer log)

"./build_mac_studio.command"

################################################################################################################
dmin@Johns-MacBook-Pro FCSP % ./build_mac_studio.command
>> Checking prerequisites…
   python3: Python 3.14.5  (/Library/Frameworks/Python.framework/Versions/3.14/bin/python3)
   arch:    arm64
>> Creating build environment…
WARNING: Cache entry deserialization failed, entry ignored
>> Installing numpy (Freeze Tail) and Apple Vision bindings (Best Play, Map Sorter)…
WARNING: Cache entry deserialization failed, entry ignored
WARNING: Cache entry deserialization failed, entry ignored
Collecting numpy
  Using cached numpy-2.5.2-cp314-cp314-macosx_14_0_arm64.whl.metadata (6.6 kB)
Collecting pyobjc-framework-Vision
  Using cached pyobjc_framework_vision-12.2.2-cp314-cp314-macosx_10_15_universal2.whl.metadata (2.6 kB)
Collecting pyobjc-framework-Quartz
  Using cached pyobjc_framework_quartz-12.2.2-cp314-cp314-macosx_10_15_universal2.whl.metadata (3.6 kB)
Collecting pyobjc-core>=12.2.2 (from pyobjc-framework-Vision)
  Using cached pyobjc_core-12.2.2-cp314-cp314-macosx_10_15_universal2.whl.metadata (2.8 kB)
Collecting pyobjc-framework-Cocoa>=12.2.2 (from pyobjc-framework-Vision)
  Using cached pyobjc_framework_cocoa-12.2.2-cp314-cp314-macosx_10_15_universal2.whl.metadata (2.6 kB)
Collecting pyobjc-framework-CoreML>=12.2.2 (from pyobjc-framework-Vision)
  Using cached pyobjc_framework_coreml-12.2.2-cp314-cp314-macosx_10_15_universal2.whl.metadata (2.5 kB)
Using cached numpy-2.5.2-cp314-cp314-macosx_14_0_arm64.whl (5.4 MB)
Using cached pyobjc_framework_vision-12.2.2-cp314-cp314-macosx_10_15_universal2.whl (16 kB)
Using cached pyobjc_framework_quartz-12.2.2-cp314-cp314-macosx_10_15_universal2.whl (219 kB)
Using cached pyobjc_core-12.2.2-cp314-cp314-macosx_10_15_universal2.whl (6.4 MB)
Using cached pyobjc_framework_cocoa-12.2.2-cp314-cp314-macosx_10_15_universal2.whl (388 kB)
Using cached pyobjc_framework_coreml-12.2.2-cp314-cp314-macosx_10_15_universal2.whl (12 kB)
Installing collected packages: pyobjc-core, numpy, pyobjc-framework-Cocoa, pyobjc-framework-Quartz, pyobjc-framework-CoreML, pyobjc-framework-Vision
Successfully installed numpy-2.5.2 pyobjc-core-12.2.2 pyobjc-framework-Cocoa-12.2.2 pyobjc-framework-CoreML-12.2.2 pyobjc-framework-Quartz-12.2.2 pyobjc-framework-Vision-12.2.2
>> Installing PyInstaller…
Collecting pyinstaller
  Using cached pyinstaller-6.22.2-py3-none-macosx_10_13_universal2.whl.metadata (8.5 kB)
Collecting altgraph (from pyinstaller)
  Using cached altgraph-0.17.5-py2.py3-none-any.whl.metadata (7.5 kB)
Collecting macholib>=1.8 (from pyinstaller)
  Using cached macholib-1.16.4-py2.py3-none-any.whl.metadata (12 kB)
Collecting packaging>=22.0 (from pyinstaller)
  Using cached packaging-26.3-py3-none-any.whl.metadata (3.5 kB)
Collecting pyinstaller-hooks-contrib>=2026.6 (from pyinstaller)
  Using cached pyinstaller_hooks_contrib-2026.7-py3-none-any.whl.metadata (16 kB)
Collecting setuptools>=42.0.0 (from pyinstaller)
  Using cached setuptools-84.0.0-py3-none-any.whl.metadata (6.6 kB)
Using cached pyinstaller-6.22.2-py3-none-macosx_10_13_universal2.whl (1.1 MB)
Using cached macholib-1.16.4-py2.py3-none-any.whl (38 kB)
Using cached altgraph-0.17.5-py2.py3-none-any.whl (21 kB)
Using cached packaging-26.3-py3-none-any.whl (129 kB)
Using cached pyinstaller_hooks_contrib-2026.7-py3-none-any.whl (459 kB)
Using cached setuptools-84.0.0-py3-none-any.whl (818 kB)
Installing collected packages: altgraph, setuptools, packaging, macholib, pyinstaller-hooks-contrib, pyinstaller
Successfully installed altgraph-0.17.5 macholib-1.16.4 packaging-26.3 pyinstaller-6.22.2 pyinstaller-hooks-contrib-2026.7 setuptools-84.0.0
   numpy and the Vision bindings import cleanly.
>> Cleaning previous build…
>> Building app…
40 INFO: PyInstaller: 6.22.2, contrib hooks: 2026.7
40 INFO: Python: 3.14.5
52 INFO: Platform: macOS-26.6.1-arm64-arm-64bit-Mach-O
52 INFO: Python environment: /Users/admin/Desktop/FCSP/.buildenv_studio
53 INFO: wrote /Users/admin/Desktop/FCSP/FanCaveStudio.spec
55 INFO: Removing temporary files and cleaning cache in /Users/john/Library/Application Support/pyinstaller
594 INFO: Module search paths (PYTHONPATH):
['/Library/Frameworks/Python.framework/Versions/3.14/lib/python314.zip',
 '/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14',
 '/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/lib-dynload',
 '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages',
 '/Users/john/Desktop/FCSP']
737 INFO: checking Analysis
737 INFO: Building Analysis because Analysis-00.toc is non existent
737 INFO: Looking for Python shared library...
741 INFO: Using Python shared library: /Library/Frameworks/Python.framework/Versions/3.14/Python
741 INFO: Running Analysis Analysis-00.toc
741 INFO: Target bytecode optimization level: 0
741 INFO: Initializing module dependency graph...
741 INFO: Initializing module graph hook caches...
748 INFO: Analyzing modules for base_library.zip ...
1620 INFO: Processing standard module hook 'hook-encodings.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
1872 INFO: Processing standard module hook 'hook-pickle.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
2049 INFO: Processing standard module hook 'hook-math.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
2149 INFO: Processing standard module hook 'hook-difflib.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
2159 INFO: Processing standard module hook 'hook-heapq.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
4070 INFO: Caching module dependency graph...
4094 INFO: Analyzing /Users/admin/Desktop/FCSP/fan_cave_studio.py
4205 INFO: Processing standard module hook 'hook-platform.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
4231 INFO: Processing standard module hook 'hook-xml.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
4264 INFO: Processing standard module hook 'hook-sysconfig.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
4275 INFO: Processing standard module hook 'hook-_osx_support.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
4279 INFO: Processing standard module hook 'hook-_ctypes.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
4380 INFO: Processing standard module hook 'hook-multiprocessing.util.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
4904 INFO: Processing standard module hook 'hook-xml.etree.cElementTree.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
5912 INFO: Processing standard module hook 'hook-numpy.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
6141 INFO: Processing pre-safe-import-module hook 'hook-typing_extensions.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks/pre_safe_import_module'
6141 INFO: SetuptoolsInfo: initializing cached setuptools info...
6851 INFO: Processing standard module hook 'hook-webbrowser.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
8594 INFO: Processing pre-find-module-path hook 'hook-tkinter.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks/pre_find_module_path'
8594 INFO: TclTkInfo: initializing cached Tcl/Tk info...
8786 INFO: Processing standard module hook 'hook-_tkinter.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
8848 INFO: Processing module hooks (post-graph stage)...
8853 INFO: Processing standard module hook 'hook-_tkinter.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks'
8922 INFO: Performing binary vs. data reclassification (204 entries)
8953 INFO: Looking for ctypes DLLs
8984 INFO: Analyzing run-time hooks ...
8986 INFO: Including run-time hook 'pyi_rth_inspect.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks/rthooks'
8988 INFO: Including run-time hook 'pyi_rth__tkinter.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks/rthooks'
8988 INFO: Including run-time hook 'pyi_rth_pkgutil.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks/rthooks'
8989 INFO: Including run-time hook 'pyi_rth_multiprocessing.py' from '/Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/hooks/rthooks'
8998 INFO: Creating base_library.zip...
9011 INFO: Looking for dynamic libraries
9236 INFO: Warnings written to /Users/admin/Desktop/FCSP/build/FanCaveStudio/warn-FanCaveStudio.txt
9252 INFO: Graph cross-reference written to /Users/admin/Desktop/FCSP/build/FanCaveStudio/xref-FanCaveStudio.html
9356 INFO: checking PYZ
9356 INFO: Building PYZ because PYZ-00.toc is non existent
9356 INFO: Building PYZ (ZlibArchive) /Users/admin/Desktop/FCSP/build/FanCaveStudio/PYZ-00.pyz
9809 INFO: Building PYZ (ZlibArchive) /Users/admin/Desktop/FCSP/build/FanCaveStudio/PYZ-00.pyz completed successfully.
9815 INFO: EXE target arch: arm64
9815 INFO: Code signing identity: None
9817 INFO: checking PKG
9817 INFO: Building PKG because PKG-00.toc is non existent
9817 INFO: Building PKG (CArchive) FanCaveStudio.pkg
9865 INFO: Building PKG (CArchive) FanCaveStudio.pkg completed successfully.
9866 INFO: Bootloader /Users/admin/Desktop/FCSP/.buildenv_studio/lib/python3.14/site-packages/PyInstaller/bootloader/Darwin-64bit/runw
9866 INFO: checking EXE
9866 INFO: Building EXE because EXE-00.toc is non existent
9866 INFO: Building EXE from EXE-00.toc
9866 INFO: Copying bootloader EXE to /Users/admin/Desktop/FCSP/build/FanCaveStudio/FanCaveStudio
9866 INFO: Converting EXE to target arch (arm64)
9894 INFO: Removing signature(s) from EXE
9912 INFO: Modifying Mach-O image UUID(s) in EXE
9916 INFO: Appending PKG archive to EXE
9918 INFO: Fixing EXE headers for code signing
9923 INFO: Re-signing the EXE
9945 INFO: Building EXE from EXE-00.toc completed successfully.
9948 INFO: checking COLLECT
9948 INFO: Building COLLECT because COLLECT-00.toc is non existent
9948 INFO: Building COLLECT COLLECT-00.toc
13902 INFO: Building COLLECT COLLECT-00.toc completed successfully.
13907 INFO: checking BUNDLE
13907 INFO: Building BUNDLE because BUNDLE-00.toc is non existent
13907 INFO: Building BUNDLE BUNDLE-00.toc
16570 INFO: Signing the BUNDLE...
16656 INFO: Building BUNDLE BUNDLE-00.toc completed successfully.
16661 INFO: Build complete! The results are available in: /Users/admin/Desktop/FCSP/dist

>> Done.  App is at:  /Users/admin/Desktop/FCSP/dist/FanCaveStudio.app
>> First launch: right-click the app > Open (unsigned-app Gatekeeper).
>> Reminder: ffmpeg must be installed (brew install ffmpeg).

Press any key to close.
#######################

Then run the app from your Finder APP from where it says above (example)

For me it was found here. Essentially one subfolder "dist" deeper and the application is yours.
"/Users/admin/Desktop/FCSP/dist/FanCaveStudio.app"






