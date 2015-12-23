#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(level=logging.DEBUG)
logging.disable(logging.DEBUG)

import subprocess
import sys
import re

private_interface_template = """
#import <objc/runtime.h>

@interface %s () <%s>
@end
"""

class_factory_template = """\n#pragma mark - class factory
+ (instancetype)classFactory:(id)obj
{
  return ^ (%s *blocks) {
    objc_setAssociatedObject(obj, &%sKey, blocks, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    return blocks;
  } ([%s new]);
}
"""

setter_impl_template = """- (void)set%sBlock:(%sBlock)block
{
  objc_setAssociatedObject(self, &%sKey, block, OBJC_ASSOCIATION_COPY);
}
"""

protocol_impl_void_template = """%s
{
  ^(%sBlock block) {
    if (block)
      block(%s);
  } (objc_getAssociatedObject(self, &%sKey));
}
"""

protocol_impl_type_template = """%s
{
  return ^(%sBlock block) {
    return (block) ? block(%s) : %s;
  } (objc_getAssociatedObject(self, &%sKey));
}
"""

class GenBlocks(object):
  """docstring for GenBlocks"""
  def __init__(self, arg):
    super(GenBlocks, self).__init__()
    self.arg = arg
    self.delimiters = re.compile(r'[ ()]')
    self.class_name = self.arg.protocol + 'Blocks'

  @staticmethod
  def default_type_value(t):
    type_lookup = {
      'BOOL' : 'NO',
      'NSInteger': '0',
      'CGFloat': '0',
      'NSString *': '@""',
      'NSString*': '@""',
      'id': 'nil'}
    return (t in type_lookup) and type_lookup[t] or 'nil'

  @staticmethod
  def ast(f, p):
    logging.debug('ast')
    cmdline = [
      'clang',
      '-cc1',
      '-ast-print',
      '-ast-dump-filter',
      p,
      '-fblocks',
      '-w',
      '-x',
      'objective-c']

    token_filter = lambda d:(d != '') and not('Printing' in d) and not('@protocol' in d) and not('@end' in d)

    proc = subprocess.Popen(cmdline, stdout=subprocess.PIPE, stdin=f, stderr=subprocess.DEVNULL)
    a = [d[:-1] for d in [l.rstrip().decode() for l in proc.stdout if l] if token_filter(d)]
    (f != sys.stdin) and f.close()
    proc.wait()
    return a

  @staticmethod
  def analize(a, r):
    logging.debug('analize')
    blocks = []
    for i in a:
      argchk = 0
      return_type = ''
      block_name = ''
      block_prototype = ''
      block_args = ''
      for n, s in enumerate([d for d in r.split(i) if d != '' and d != '-']):
        if n == 0:
          return_type = s
        elif n == 1:
          if s == '*':
            return_type = return_type + '*'
          else:
            block_name = s[0].upper() + s[1:-1]
        else:
          if ':' in s:
            block_name = block_name + s[0].upper() + s[1:-1]
            argchk = 0
          elif s == '*':
            block_prototype = block_prototype + '*'
          else:
            if argchk == 0:
              block_prototype = block_prototype + s + ' '
              argchk += 1;
            else:
              block_prototype = block_prototype + s + ', '
              block_args = block_args + s + ', '

      blocks.append({
        'type': return_type,
        'name': block_name,
        'prototype': block_prototype[:-2],
        'args': block_args[:-2]})

    return blocks

  def load(self):
    logging.debug('load')
    self.methods = self.ast(self.arg.input and open(self.arg.input, 'r') or sys.stdin, self.arg.protocol)
    self.blocks = self.analize(self.methods, self.delimiters)
    return self

  def emit(self):
    logging.debug('emit')
    print('// %s Block typedefs\n' % self.arg.protocol)
    for i in self.blocks:
      print('#ifdef USE_%sBlock' % (i['name']))
      print('typedef %s (^%sBlock)(%s);' % (i['type'], i['name'], i['prototype']))
      print('#endif')

    print('\n#pragma mark - %s Block setter definitions\n' % self.arg.protocol)
    for i in self.blocks:
      print('#ifdef USE_%sBlock' % (i['name']))
      print('- (void)set%sBlock:(%sBlock)block;' % (i['name'], i['name']))
      print('#endif')

    print(private_interface_template % (self.arg.classname, self.arg.protocol))

    print('static char %sKey;\n' % self.arg.classname)

    print('\n// %s Block keys\n' % self.arg.protocol)
    for i in self.blocks:
      print('#ifdef USE_%sBlock' % (i['name']))
      print('static char %sKey;' % i['name'])
      print('#endif')

    print(class_factory_template % (self.arg.classname, self.arg.classname, self.arg.classname))

    print('\n#pragma mark - %s Block setters\n' % self.arg.protocol)
    for i in self.blocks:
      print('#ifdef USE_%sBlock' % (i['name']))
      print(setter_impl_template % (i['name'], i['name'], i['name']))
      print('#endif')

    print('#pragma mark - %s\n' % self.arg.protocol)
    for n, i in enumerate(self.blocks):
      if i['type'] == 'void':
        print('#ifdef USE_%sBlock' % (i['name']))
        print(protocol_impl_void_template % (self.methods[n], i['name'], i['args'], i['name']))
        print('#endif')
      else:
        print('#ifdef USE_%sBlock' % (i['name']))
        print(protocol_impl_type_template % (self.methods[n], i['name'], i['args'], self.default_type_value(i['type']), i['name']))
        print('#endif')


def main():
  import argparse
  def prepare_args(ap):
    ap.add_argument('protocol', help='Objective-C protocol name')
    ap.add_argument('classname', help='Objective-C generate class name')
    ap.add_argument('-i', '--input', default='', help='Objective-C protocol header file')
    ap.add_argument('-o', '--output', default='', help='generating output file name')
    ap.add_argument('-d', '--folder', default='', help='output folder')
    return ap
  args = prepare_args(argparse.ArgumentParser()).parse_args()

  # logging.debug('input file: [%s]' % args.input)
  # logging.debug('output name: [%s]' % args.output)
  # logging.debug('protocol: [%s]' % args.protocol)

  GenBlocks(args).load().emit()

  return 0

if __name__ == '__main__':
  sys.exit(main())
