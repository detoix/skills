# Native Windows

Run the bundled Python launcher directly on Windows. Use a 64-bit Python interpreter and a matching native C++ toolchain. Downloads, source, Release builds, executables, DLLs, and installation metadata stay in the skill's ignored `.runtime/` directory. A runtime compiled for another operating system is not a Windows installation.

## Prepare the host

Resolve the actual skill and project paths before running commands. In PowerShell, inspect `Get-Command py, git, cmake, curl.exe, ffmpeg, ffprobe` and `py -3 --version`. Install missing tools using an available Windows package manager or their official installers within the user's authorized scope. The Python helpers need only the standard library.

Install Visual Studio Build Tools with **Desktop development with C++**, including an MSVC toolset and a Windows SDK. The full Visual Studio IDE is optional. See Microsoft's [C++ Build Tools instructions](https://learn.microsoft.com/en-us/cpp/build/building-on-the-command-line). With CMake's Visual Studio generator, CMake discovers the installed toolchain; an explicitly selected Ninja generator needs the matching x64 Developer PowerShell environment. Avoid hardcoding the Visual Studio edition or installation directory.

Use CMake 3.19 or newer and a version that supports the installed Visual Studio release. Keep Git, CMake, Python, curl, FFmpeg, and ffprobe available to the same process. In subprocesses, `curl` resolves to its executable rather than PowerShell's alias.

## Build and verify

From the repository root, this PowerShell example resolves the existing skill directory:

```powershell
$YueSkill = (Resolve-Path '.\yue-music').Path
py -3 "$YueSkill\scripts\yue.py" setup --build-only --jobs 2
py -3 "$YueSkill\scripts\yue.py" check --binaries-only
```

These commands download the pinned source and compile the native tools without fetching model weights or performing inference. The installer selects Release configuration, collects `.exe` files and accompanying `.dll` files, then checks their usage output. It handles both a top-level build output and a `Release` subdirectory. A failed installation check restores the prior binary directory.

To download and verify the required weights, run ordinary setup:

```powershell
py -3 "$YueSkill\scripts\yue.py" setup --jobs 2
py -3 "$YueSkill\scripts\yue.py" check --hash
```

The launcher uses a Windows file lock, puts the runtime DLL directory on the child's `PATH`, and starts synthesis below normal priority. Keep generated requests, scores, logs, and recordings in the user's project. Pass paths as separate quoted arguments, including paths containing spaces. Generation and replay use the same subcommands and JSON schema as on other platforms; invoke them with `py -3` and PowerShell path syntax.

## Optional GPU builds

For Vulkan, install a compatible Windows GPU driver and Vulkan SDK with `glslc` and SPIR-V headers, open a terminal with the SDK environment available, and inspect `vulkaninfo --summary`. Build with `setup --backend vulkan --jobs 2`; verify the actual hardware device before selecting it for generation. A successful CPU build does not establish GPU availability.

For CUDA, install an NVIDIA driver and CUDA toolkit compatible with the selected MSVC toolset, then use `setup --backend cuda --jobs 2`. Follow the [backend verification procedure](runtime.md#select-and-verify-a-backend) before a long render. The optional `--mkl-root` procedure currently targets GNU C++ on Linux.

## Maintainer checks

Run `py -3 -m unittest discover -s yue-music/tests -v` from the repository root. On a Windows host, also run the build-only and binaries-only checks above. Passing tests on another operating system does not establish native Windows behavior. GPU generation requires validation on the intended hardware.
