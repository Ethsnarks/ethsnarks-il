cmake_minimum_required(VERSION 3.8)
project(ethsnarks-il)
add_subdirectory(../ethsnarks ../.build/ethsnarks EXCLUDE_FROM_ALL)

add_library(ethsnarks_il STATIC
	circuit_reader.cpp
)
target_link_libraries(ethsnarks_il ethsnarks_common)

add_executable(il-pinocchio main.cpp)
target_link_libraries(il-pinocchio ethsnarks_il)

add_executable(il-jsnark_test jsnark_test.cpp)
target_link_libraries(il-jsnark_test ethsnarks_il)
