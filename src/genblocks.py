#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(level=logging.DEBUG)
# logging.disable(logging.DEBUG)

import subprocess
import sys
import re

interface_header = """
//
// %s.h
//
"""

interface_begin_template = """
@interface %s : NSObject

#pragma mark - class factory

+ (instancetype)classFactory:(id)obj;"""

interface_end_template = """
@end"""

property_impl_template = """@property (copy, nonatomic) %sBlock %sBlock;"""

implementation_header = """
//
// %s.m
//
"""

private_interface_template = """#import "%s.h"
#import <objc/runtime.h>

@interface %s () <%s>
@end
"""

implementation_begin_template = """@implementation %s

static char %sKey;\n"""

implementation_end_template = """@end"""

class_factory_template = """#pragma mark - class factory

+ (instancetype)classFactory:(id)obj
{
  return ^(%s *blocks) {
    //obl.delegate = blocks;
    //obj.dataSource = blocks;
    objc_setAssociatedObject(obj, &%sKey, blocks, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    return blocks;
  } ([%s new]);
}
"""

protocol_impl_void_template = """#ifdef USE_%sBlock
%s
{
  if (self.%sBlock) {
    self.%sBlock(%s);
  }
}
#endif
"""

protocol_impl_type_template = """#ifdef USE_%sBlock
%s
{
  return self.%sBlock ? self.%sBlock(%s) : %s;
}
#endif
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
      'CGSize': 'CGSizeZero',
      'UIEdgeInsets': 'UIEdgeInsetsZero',
      'UITableViewCellEditingStyle': 'UITableViewCellEditingStyleNone',
      'id': 'nil'}
    return (t in type_lookup) and type_lookup[t] or 'nil'

  @staticmethod
  def ast(f, p, r):
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
      'objective-c',
      '-isysroot',
      r]

    token_filter = lambda d:(d != '') and not('Printing' in d) and not('@protocol' in d) and not('@end' in d)

    proc = subprocess.Popen(cmdline,
                            stdout=subprocess.PIPE,
                            stdin=f,
                            stderr=subprocess.DEVNULL)

    a = [d[:-1] for d in [l.rstrip().decode() for l in proc.stdout if l] if token_filter(d)]
    (f != sys.stdin) and f.close()
    proc.wait()
    return a

  @staticmethod
  def analize(a, r):
    logging.debug('analize')
    blocks = []
    for i in a:
      argstep = 0
      return_type = ''
      block_name = ''
      block_prototype = ''
      block_args = ''
      for n, s in enumerate([d for d in r.split(i) if d != '' and d != '-']):
        logging.debug('n:%d argstep:%d token:[%s]' % (n, argstep, s))
        if n == 0:
          if s != 'nonnull' and s != 'nullable':
            return_type = s
        elif n == 1:
          if s == '*':
            return_type = return_type + '*'
          else:
            if s[0:2] != 'NS' and s[0:2] != 'UI' and s[0:2] != 'id':
              block_name = s[0].upper() + s[1:-1]
            else:
              return_type = return_type + s
        elif n == 2:
          if s == '*':
             return_type = return_type + '*'
        else:
          if ':' in s:
            block_name = block_name + s[0].upper() + s[1:-1]
            argstep = 0
          elif s == '*':
            block_prototype = block_prototype + '*'
          elif s == '__attribute__':
            break
          else:
            if argstep == 0:
              if s != 'nonnull' and s != 'nullable':
                block_prototype = block_prototype + s + ' '
                argstep += 1
            else:
              block_prototype = block_prototype + s + ', '
              if s[0:2] != 'NS' and s[0:2] != 'UI':
                block_args = block_args + s + ', '

      blocks.append({
        'type': return_type,
        'name': block_name,
        'prototype': block_prototype[:-2],
        'args': block_args[:-2]})

    return blocks

  def load(self):
    logging.debug('load')
    self.methods = self.ast(self.arg.input and open(self.arg.input, 'r') or sys.stdin, self.arg.protocol, self.arg.sysroot)
    self.blocks = self.analize(self.methods, self.delimiters)
    return self

  def emit(self):
    logging.debug('emit')

    to_downcase_first_char = lambda s: s[:1].lower() + s[1:] if s else ''

    print(interface_header % (self.arg.classname))

    print('// %s Blocks typedefs\n' % (self.arg.protocol))
    for i in self.blocks:
      print('#ifdef USE_%sBlock' % (i['name']))
      print('typedef %s (^%sBlock)(%s);' % (i['type'], i['name'], i['prototype']))
      print('#endif')

    print(interface_begin_template % (self.arg.classname))

    print('\n#pragma mark - %s Blocks properties\n' % self.arg.protocol)
    for i in self.blocks:
      print('#ifdef USE_%sBlock' % (i['name']))
      print(property_impl_template % (i['name'], to_downcase_first_char(i['name'])))
      print('#endif')

    print(interface_end_template)

    print(implementation_header % (self.arg.classname))

    print(private_interface_template % (self.arg.classname, self.arg.classname, self.arg.protocol))

    print(implementation_begin_template % (self.arg.classname, self.arg.classname))

    print(class_factory_template % (self.arg.classname, self.arg.classname, self.arg.classname))

    print('#pragma mark - %s\n' % self.arg.protocol)
    for n, i in enumerate(self.blocks):
      logging.debug('arguments:%s' % i['args'])
      dcname = to_downcase_first_char(i['name'])
      if i['type'] == 'void':
        print(protocol_impl_void_template % (i['name'], self.methods[n], dcname, dcname, i['args']))
      else:
        logging.debug('type:[%s]' % i['type'])
        print(protocol_impl_type_template % (i['name'], self.methods[n], dcname, dcname, i['args'], self.default_type_value(i['type'].strip())))

    print(implementation_end_template)

def main():
  import argparse
  def prepare_args(ap):
    ap.add_argument('sysroot', help='option for clang -isysroot')
    ap.add_argument('protocol', help='Objective-C protocol name')
    ap.add_argument('classname', help='Objective-C generate class name')
    ap.add_argument('-i', '--input', default='', help='Objective-C protocol header file')
    # ap.add_argument('-o', '--output', default='', help='generating output file name')
    # ap.add_argument('-d', '--folder', default='', help='output folder')
    return ap
  args = prepare_args(argparse.ArgumentParser()).parse_args()

  # logging.debug('input file: [%s]' % args.input)
  # logging.debug('output name: [%s]' % args.output)
  # logging.debug('protocol: [%s]' % args.protocol)

  GenBlocks(args).load().emit()

  return 0

if __name__ == '__main__':
  sys.exit(main())
