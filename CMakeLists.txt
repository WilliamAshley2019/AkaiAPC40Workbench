cmake_minimum_required(VERSION 3.22)
project(APC40Workbench VERSION 0.1.0)

# Point this at your JUCE 8.0.12 checkout:  cmake -B build -DJUCE_DIR=C:/JUCE
set(JUCE_DIR "" CACHE PATH "Path to JUCE 8.0.12 source tree")
if(NOT JUCE_DIR OR NOT EXISTS "${JUCE_DIR}/CMakeLists.txt")
    message(FATAL_ERROR "Set -DJUCE_DIR=<path to JUCE 8.0.12>")
endif()
add_subdirectory(${JUCE_DIR} JUCE)

juce_add_gui_app(APC40Workbench
    PRODUCT_NAME "APC40 Workbench"
    COMPANY_NAME "AlphaAudio")

# apc40_layout.json is embedded; a copy placed next to the .exe overrides it.
juce_add_binary_data(ApcLayoutData SOURCES apc40_layout.json)

target_sources(APC40Workbench PRIVATE
    Source/Main.cpp Source/MainComponent.h Source/ApcSurface.h Source/ApcLayout.h)

target_compile_definitions(APC40Workbench PRIVATE
    JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0
    JUCE_APPLICATION_NAME_STRING="$<TARGET_PROPERTY:APC40Workbench,JUCE_PRODUCT_NAME>"
    JUCE_APPLICATION_VERSION_STRING="$<TARGET_PROPERTY:APC40Workbench,JUCE_VERSION>")

target_link_libraries(APC40Workbench
    PRIVATE ApcLayoutData juce::juce_gui_basics juce::juce_audio_devices
    PUBLIC  juce::juce_recommended_config_flags juce::juce_recommended_lto_flags
            juce::juce_recommended_warning_flags)
