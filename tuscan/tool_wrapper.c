/* Tuscan native tool wrapper
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
 * This file is a Jinja template that is filled out by the
 * install_bootstrap stage. One such file will be generated for each
 * native tool that will need to be redirected to a toolchain tool in
 * accordance with the rules specified in
 * toolchains/make_package/TOOLCHAIN/tool_redirect_rules.yaml.
 */

#include <stdlib.h>
#include <stdio.h>
#include <unistd.h>

int main(int argc, char **argv) {
  int fd = mkstemp("/tmp/tuscan-native-XXXXXX");
  if (fd == -1) {
    perror("tuscan: mkstemp");
    return 1;
  }
  dprintf(fd, "{{ native_program }}\n");
  if (close(fd) == -1) {
    perror("tuscan: close");
    return 1;
  }

  char *toolchain_tool = "{{ toolchain_bin }}/{{ toolchain_program }}";
  char *new_argv[argc];
  new_argv[0] = toolchain_tool;
  for(int i = 1; i < argc; i++) {
    new_argv[i] = argv[i];
  }
  execv(toolchain_tool, new_argv);
}
