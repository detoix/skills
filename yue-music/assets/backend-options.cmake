# Included after project(ggml), before its backend subdirectories.
# Keep the selected BLAS threading runtime consistent with GGML's OpenMP.
if(YUE_MKL_ROOT)
    if(NOT CMAKE_CXX_COMPILER_ID STREQUAL "GNU" OR NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
        message(FATAL_ERROR "--mkl-root currently supports GNU C++ on Linux; use OpenBLAS with other toolchains")
    endif()
    find_package(OpenMP REQUIRED COMPONENTS CXX)
    unset(YUE_MKL_INCLUDE CACHE)
    find_path(YUE_MKL_INCLUDE mkl.h HINTS "${YUE_MKL_ROOT}/include" NO_DEFAULT_PATH REQUIRED)
    foreach(component intel_lp64 gnu_thread core)
        unset(YUE_MKL_${component} CACHE)
        find_library(YUE_MKL_${component}
            NAMES mkl_${component} libmkl_${component}.so.2
            HINTS "${YUE_MKL_ROOT}/lib" "${YUE_MKL_ROOT}/lib/intel64" "${YUE_MKL_ROOT}/lib/intel64_lin"
            NO_DEFAULT_PATH REQUIRED)
    endforeach()
    set(BLAS_INCLUDE_DIRS "${YUE_MKL_INCLUDE}" CACHE PATH "MKL headers" FORCE)
    set(BLAS_LIBRARIES "${YUE_MKL_intel_lp64};${YUE_MKL_gnu_thread};${YUE_MKL_core};OpenMP::OpenMP_CXX;m;dl;pthread"
        CACHE STRING "Threaded MKL libraries" FORCE)
endif()

# Narrow Windows argv and file APIs must agree with GGML's UTF-8 filenames.
# CMake embeds .manifest target sources with MSVC and clang-cl linkers.
if(WIN32 AND MSVC)
    function(yue_windows_utf8_manifest)
        foreach(tool yue-plan yue-synth yue-server)
            if(TARGET ${tool})
                target_sources(${tool} PRIVATE "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/windows-utf8.manifest")
            endif()
        endforeach()
    endfunction()
    cmake_language(DEFER DIRECTORY "${CMAKE_SOURCE_DIR}" CALL yue_windows_utf8_manifest)
endif()

if(GGML_VULKAN)
    # Prefer a real package, including a package supplied by the Vulkan SDK.
    if(DEFINED ENV{VULKAN_SDK} AND NOT "$ENV{VULKAN_SDK}" STREQUAL "")
        find_package(SPIRV-Headers CONFIG QUIET HINTS "$ENV{VULKAN_SDK}")
    else()
        find_package(SPIRV-Headers CONFIG QUIET)
    endif()
    if(NOT SPIRV-Headers_FOUND)
        if(DEFINED YUE_SPIRV_HEADERS_INCLUDE AND
           NOT EXISTS "${YUE_SPIRV_HEADERS_INCLUDE}/spirv/unified1/spirv.hpp")
            unset(YUE_SPIRV_HEADERS_INCLUDE CACHE)
            unset(YUE_SPIRV_HEADERS_INCLUDE)
        endif()
        find_path(YUE_SPIRV_HEADERS_INCLUDE
            NAMES spirv/unified1/spirv.hpp
            HINTS "$ENV{VULKAN_SDK}/Include" "$ENV{VULKAN_SDK}/include" ${Vulkan_INCLUDE_DIRS}
            DOC "SPIR-V headers supplied by the selected Vulkan SDK")
        if(NOT YUE_SPIRV_HEADERS_INCLUDE)
            message(FATAL_ERROR "SPIR-V headers were not found. Install the Vulkan SDK headers or provide SPIRV-Headers_DIR.")
        endif()
        # Pinned GGML repeats a REQUIRED config lookup in its Vulkan subdirectory.
        # A build-local config lets an SDK include tree satisfy that same lookup.
        file(TO_CMAKE_PATH "${YUE_SPIRV_HEADERS_INCLUDE}" YUE_SPIRV_HEADERS_INCLUDE)
        set(_yue_spirv_config_dir "${CMAKE_CURRENT_BINARY_DIR}/yue-spirv-headers")
        file(MAKE_DIRECTORY "${_yue_spirv_config_dir}")
        configure_file("${CMAKE_CURRENT_LIST_DIR}/spirv-headers-config.cmake.in"
            "${_yue_spirv_config_dir}/SPIRV-HeadersConfig.cmake" @ONLY)
        set(SPIRV-Headers_DIR "${_yue_spirv_config_dir}" CACHE PATH "Build-local SPIR-V headers config" FORCE)
        find_package(SPIRV-Headers CONFIG REQUIRED)
    endif()
    if(NOT TARGET SPIRV-Headers::SPIRV-Headers)
        message(FATAL_ERROR "The SPIRV-Headers config did not define SPIRV-Headers::SPIRV-Headers.")
    endif()
    # Older Vulkan SDK headers do not transitively include the SPIR-V enum header.
    # This affects compilation only; no compute kernels are changed.
    function(yue_vulkan_spirv_headers)
        if(TARGET ggml-vulkan)
            target_link_libraries(ggml-vulkan PRIVATE SPIRV-Headers::SPIRV-Headers)
            if(MSVC)
                target_compile_options(ggml-vulkan PRIVATE /FIspirv/unified1/spirv.hpp)
            else()
                target_compile_options(ggml-vulkan PRIVATE -include spirv/unified1/spirv.hpp)
            endif()
        endif()
    endfunction()
    cmake_language(DEFER CALL yue_vulkan_spirv_headers)
endif()
