# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

# Runs on buildbot slave, creating a release package using the build
# system and zipping it into buildbot_upload.zip. This is then uploaded
# to the master in the next buildbot step.

import os
import subprocess
import sys
import zipfile

# get builder name
if len(sys.argv) < 2:
    sys.stderr.write("Not enough arguments, expecting builder name\n")
    sys.exit(1)

builder = sys.argv[1]
# Never write branch if it is master.
branch = sys.argv[2] if (len(sys.argv) >= 3 and sys.argv[2] != 'master') else ''

blender_dir = os.path.join('..', 'blender.git')
build_dir = os.path.join('..', 'build', builder)
install_dir = os.path.join('..', 'install', builder)
buildbot_upload_zip = os.path.abspath(os.path.join(os.path.dirname(install_dir), "buildbot_upload.zip"))

upload_filename = None  # Name of the archive to be uploaded
                        # (this is the name of archive which will appear on the
                        # download page)
upload_filepath = None  # Filepath to be uploaded to the server
                        # (this folder will be packed)


def parse_header_file(filename, define):
    import re
    regex = re.compile("^#\s*define\s+%s\s+(.*)" % define)
    with open(filename, "r") as file:
        for l in file:
            match = regex.match(l)
            if match:
                return match.group(1)
    return None


# Make sure install directory always exists
if not os.path.exists(install_dir):
    os.makedirs(install_dir)


# scons does own packaging
if builder.find('scons') != -1:
    python_bin = 'python'
    if builder.find('linux') != -1:
        python_bin = '/opt/lib/python-2.7/bin/python2.7'

    os.chdir('../blender.git')
    scons_options = ['BF_QUICK=slnt', 'BUILDBOT_BRANCH=' + branch, 'buildslave', 'BF_FANCY=False']

    buildbot_dir = os.path.dirname(os.path.realpath(__file__))
    config_dir = os.path.join(buildbot_dir, 'config')

    if builder.find('linux') != -1:
        scons_options += ['WITH_BF_NOBLENDER=True', 'WITH_BF_PLAYER=False',
                          'BF_BUILDDIR=' + build_dir,
                          'BF_INSTALLDIR=' + install_dir,
                          'WITHOUT_BF_INSTALL=True']

        config = None
        bits = None

        if builder.endswith('linux_glibc211_x86_64_scons'):
            config = 'user-config-glibc211-x86_64.py'
            chroot_name = 'buildbot_squeeze_x86_64'
            bits = 64
        elif builder.endswith('linux_glibc211_i386_scons'):
            config = 'user-config-glibc211-i686.py'
            chroot_name = 'buildbot_squeeze_i686'
            bits = 32

        if config is not None:
            config_fpath = os.path.join(config_dir, config)
            scons_options.append('BF_CONFIG=' + config_fpath)

        blender = os.path.join(install_dir, 'blender')
        blenderplayer = os.path.join(install_dir, 'blenderplayer')
        subprocess.call(['schroot', '-c', chroot_name, '--', 'strip', '--strip-all', blender, blenderplayer])

        extra = "/home/sources/release-builder/extra/"
        mesalibs = os.path.join(extra, 'mesalibs%d.tar.bz2' % bits)
        software_gl = os.path.join(extra, 'blender-softwaregl')

        os.system('tar -xpf %s -C %s' % (mesalibs, install_dir))
        os.system('cp %s %s' % (software_gl, install_dir))
        os.system('chmod 755 %s' % (os.path.join(install_dir, 'blender-softwaregl')))

        retcode = subprocess.call(['schroot', '-c', chroot_name, '--', python_bin, 'scons/scons.py'] + scons_options)

        sys.exit(retcode)
    else:
        if builder.find('win') != -1:
            bitness = '32'

            if builder.find('win64') != -1:
                bitness = '64'

            scons_options.append('BF_INSTALLDIR=' + install_dir)
            scons_options.append('BF_BUILDDIR=' + build_dir)
            scons_options.append('BF_BITNESS=' + bitness)
            scons_options.append('WITH_BF_CYCLES_CUDA_BINARIES=True')
            scons_options.append('BF_CYCLES_CUDA_NVCC=nvcc.exe')
            if builder.find('mingw') != -1:
                scons_options.append('BF_TOOLSET=mingw')
            if builder.endswith('vc2013'):
                scons_options.append('MSVS_VERSION=12.0')
                scons_options.append('MSVC_VERSION=12.0')

        elif builder.find('mac') != -1:
            if builder.find('x86_64') != -1:
                config = 'user-config-mac-x86_64.py'
            else:
                config = 'user-config-mac-i386.py'

            scons_options.append('BF_CONFIG=' + os.path.join(config_dir, config))

        retcode = subprocess.call([python_bin, 'scons/scons.py'] + scons_options)
        sys.exit(retcode)
else:
    # CMake
    if 'win' in builder:
        os.chdir(build_dir)

        files = [f for f in os.listdir('.') if os.path.isfile(f) and f.endswith('.zip')]
        for f in files:
            os.remove(f)
        retcode = subprocess.call(['cpack', '-G', 'ZIP'])
        result_file = [f for f in os.listdir('.') if os.path.isfile(f) and f.endswith('.zip')][0]

        # TODO(sergey): Such magic usually happens in SCon's packaging but we don't have it
        # in the CMake yet. For until then we do some magic here.
        tokens = result_file.split('-')
        blender_version = tokens[1].split('.')
        blender_full_version = '.'.join(blender_version[0:2])
        git_hash = tokens[2].split('.')[1]
        platform = builder.split('_')[0]
        builderified_name = 'blender-{}-{}-{}'.format(blender_full_version, git_hash, platform)
        if branch != '':
            builderified_name = branch + "-" + builderified_name

        os.rename(result_file, "{}.zip".format(builderified_name))
        # create zip file
        try:
            if os.path.exists(buildbot_upload_zip):
                os.remove(buildbot_upload_zip)
            z = zipfile.ZipFile(buildbot_upload_zip, "w", compression=zipfile.ZIP_STORED)
            z.write("{}.zip".format(builderified_name))
            z.close()
            sys.exit(retcode)
        except Exception as ex:
            sys.stderr.write('Create buildbot_upload.zip failed' + str(ex) + '\n')
            sys.exit(1)

    elif builder.startswith('linux_'):
        blender = os.path.join(install_dir, 'blender')
        blenderplayer = os.path.join(install_dir, 'blenderplayer')

        buildinfo_h = os.path.join(build_dir, "source", "creator", "buildinfo.h")
        blender_h = os.path.join(blender_dir, "source", "blender", "blenkernel", "BKE_blender.h")

        # Get version information
        blender_version = int(parse_header_file(blender_h, 'BLENDER_VERSION'))
        blender_version = "%d.%d" % (blender_version / 100, blender_version % 100)
        blender_hash = parse_header_file(buildinfo_h, 'BUILD_HASH')[1:-1]
        blender_glibc = builder.split('_')[1]

        if builder.endswith('x86_64_cmake'):
            chroot_name = 'buildbot_squeeze_x86_64'
            bits = 64
            blender_arch = 'x86_64'
        elif builder.endswith('i386_cmake'):
            chroot_name = 'buildbot_squeeze_i686'
            bits = 32
            blender_arch = 'i686'

        # Strip all unused symbols from the binaries
        print("Stripping binaries...")
        chroot_prefix = ['schroot', '-c', chroot_name, '--']
        subprocess.call(chroot_prefix + ['strip', '--strip-all', blender, blenderplayer])

        print("Stripping python...")
        py_target = os.path.join(install_dir, blender_version)
        subprocess.call(chroot_prefix + ['find', py_target, '-iname', '*.so', '-exec', 'strip', '-s', '{}', ';'])

        # Copy all specific files which are too specific to be copied by
        # the CMake rules themselves
        print("Copying extra scripts and libs...")

        extra = '/' + os.path.join('home', 'sources', 'release-builder', 'extra')
        mesalibs = os.path.join(extra, 'mesalibs' + str(bits) + '.tar.bz2')
        software_gl = os.path.join(blender_dir, 'release', 'bin', 'blender-softwaregl')
        icons = os.path.join(blender_dir, 'release', 'freedesktop', 'icons')

        os.system('tar -xpf %s -C %s' % (mesalibs, install_dir))
        os.system('cp %s %s' % (software_gl, install_dir))
        os.system('cp -r %s %s' % (icons, install_dir))
        os.system('chmod 755 %s' % (os.path.join(install_dir, 'blender-softwaregl')))

        # Construct archive name
        upload_filename = 'blender-%s-%s-linux-%s-%s.tar.bz2' % (blender_version,
                                                                 blender_hash,
                                                                 blender_glibc,
                                                                 blender_arch)
        if branch != '':
            upload_filename = branch + "-" + upload_filename

        print("Creating .tar.bz2 archive")
        os.system('tar -C../install -cjf ../install/%s.tar.bz2 %s' % (builder, builder))
        upload_filepath = install_dir + '.tar.bz2'


if upload_filepath is None:
    # clean release directory if it already exists
    release_dir = 'release'

    if os.path.exists(release_dir):
        for f in os.listdir(release_dir):
            if os.path.isfile(os.path.join(release_dir, f)):
                os.remove(os.path.join(release_dir, f))

    # create release package
    try:
        subprocess.call(['make', 'package_archive'])
    except Exception as ex:
        sys.stderr.write('Make package release failed' + str(ex) + '\n')
        sys.exit(1)

    # find release directory, must exist this time
    if not os.path.exists(release_dir):
        sys.stderr.write("Failed to find release directory %r.\n" % release_dir)
        sys.exit(1)

    # find release package
    file = None
    filepath = None

    for f in os.listdir(release_dir):
        rf = os.path.join(release_dir, f)
        if os.path.isfile(rf) and f.startswith('blender'):
            file = f
            filepath = rf

    if not file:
        sys.stderr.write("Failed to find release package.\n")
        sys.exit(1)

    upload_filename = file
    upload_filepath = filepath

# create zip file
try:
    upload_zip = os.path.join(buildbot_upload_zip)
    if os.path.exists(upload_zip):
        os.remove(upload_zip)
    z = zipfile.ZipFile(upload_zip, "w", compression=zipfile.ZIP_STORED)
    z.write(upload_filepath, arcname=upload_filename)
    z.close()
except Exception as ex:
    sys.stderr.write('Create buildbot_upload.zip failed' + str(ex) + '\n')
    sys.exit(1)
