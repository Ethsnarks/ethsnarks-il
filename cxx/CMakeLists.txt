cmake_minimum_required(VERSION 3.8)
project(ethsnarks-il)
add_subdirectory(../ethsnarks ../.build/ethsnarks EXCLUDE_FROM_ALL)


if (CMAKE_VERSION VERSION_GREATER "3.0")
  set(CMAKE_CXX_STANDARD 11)
  set(CMAKE_CXX_STANDARD_REQUIRED ON) #...is required...
else()
  include(CheckCXXCompilerFlag)
  CHECK_CXX_COMPILER_FLAG("-std=c++11" COMPILER_SUPPORTS_CXX11)

  if(COMPILER_SUPPORTS_CXX11)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11")
  elseif(COMPILER_SUPPORTS_CXX0X)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++0x")
  else()
        message(STATUS "The compiler ${CMAKE_CXX_COMPILER} has no C++11 support. Please use a different C++ compiler.")
  endif()
endif()


add_library(ethsnarks_il STATIC
	circuit_reader.cpp
)
target_link_libraries(ethsnarks_il ethsnarks_common)

add_executable(il-pinocchio main.cpp)
target_link_libraries(il-pinocchio ethsnarks_il)

add_executable(il-jsnark_test jsnark_test.cpp)
target_link_libraries(il-jsnark_test ethsnarks_il)
