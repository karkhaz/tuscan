/* Tuscan compiler wrapper
 *
 * Copyright 2016 Kareem Khazem. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * This file is a Jinja template that is filled out by
 * tuscan/wrapper_gen.py. One such file will be generated for each
 * native tool that will need to be redirected to a toolchain tool in
 * accordance with the rules specified in
 * toolchains/make_package/TOOLCHAIN/binutil_transforms.yaml.
 */

#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>
#include <syscall.h>

#define RANDOM_PATH_LENGTH 20
#define TOOLCHAIN_TOOL "{{ toolchain_bin }}/{{ toolchain_program }}"

int main(unsigned argc, char *argv[]){
  unsigned buf[RANDOM_PATH_LENGTH];
  if (syscall(SYS_getrandom, buf, RANDOM_PATH_LENGTH, 0) == -1){
    perror("tuscan: compiler wrapper: getrandom");
    exit(1);
  }
  char f_name[32];
  sprintf(f_name, "/tmp/tuscan-native-%d", abs((int)(*buf)));

  FILE *fp;
  if (!(fp = fopen(f_name, "w"))){
    perror("tuscan: compiler wrapper: fopen");
    exit(1);
  }
  fprintf(fp, "{{ native_program }}\n");
  if (fclose(fp) == EOF){
    perror("tuscan: compiler wrapper: fclose");
    exit(1);
  }

  char toolchain_tool[sizeof(TOOLCHAIN_TOOL)] = TOOLCHAIN_TOOL;
  char *new_argv[argc];
  unsigned i;
  new_argv[0] = toolchain_tool;
  for(i = 1; i < argc; i++){
    new_argv[i] = argv[i];
  }
  execv(toolchain_tool, new_argv);
}
