#!/usr/bin/env python3
# SPDX-License-Identifier: ((GPL-2.0 WITH Linux-syscall-note) OR BSD-3-Clause)

import argparse
import collections
import filecmp
import pathlib
import os
import re
import shutil
import sys
import tempfile
import yaml

sys.path.append(pathlib.Path(__file__).resolve().parent.as_posix())
from lib import SpecFamily, SpecAttrSet, SpecAttr, SpecOperation, SpecEnumSet, SpecEnumEntry
from lib import SpecSubMessage, SpecSubMessageFormat


def c_upper(name):
    return name.upper().replace('-', '_')


def c_lower(name):
    return name.lower().replace('-', '_')


def limit_to_number(name):
    """
    Turn a string limit like u32-max or s64-min into its numerical value
    """
    if name[0] == 'u' and name.endswith('-min'):
        return 0
    width = int(name[1:-4])
    if name[0] == 's':
        width -= 1
    value = (1 << width) - 1
    if name[0] == 's' and name.endswith('-min'):
        value = -value - 1
    return value


class BaseNlLib:
    def get_family_id(self):
        return 'ys->family_id'


class Type(SpecAttr):
    def __init__(self, family, attr_set, attr, value):
        super().__init__(family, attr_set, attr, value)

        self.attr = attr
        self.attr_set = attr_set
        self.type = attr['type']
        self.checks = attr.get('checks', {})

        self.request = False
        self.reply = False

        self.is_selector = False

        if 'len' in attr:
            self.len = attr['len']

        if 'nested-attributes' in attr:
            nested = attr['nested-attributes']
        elif 'sub-message' in attr:
            nested = attr['sub-message']
        else:
            nested = None

        if nested:
            self.nested_attrs = nested
            if self.nested_attrs == family.name:
                self.nested_render_name = c_lower(f"{family.ident_name}")
            else:
                self.nested_render_name = c_lower(f"{family.ident_name}_{self.nested_attrs}")

            if self.nested_attrs in self.family.consts:
                self.nested_struct_type = 'struct ' + self.nested_render_name + '_'
            else:
                self.nested_struct_type = 'struct ' + self.nested_render_name

        self.c_name = c_lower(self.name)
        if self.c_name in _C_KW:
            self.c_name += '_'
        if self.c_name[0].isdigit():
            self.c_name = '_' + self.c_name

        # Added by resolve():
        self.enum_name = None
        delattr(self, "enum_name")

    def _get_real_attr(self):
        # if the attr is for a subset return the "real" attr (just one down, does not recurse)
        return self.family.attr_sets[self.attr_set.subset_of][self.name]

    def set_request(self):
        self.request = True
        if self.attr_set.subset_of:
            self._get_real_attr().set_request()

    def set_reply(self):
        self.reply = True
        if self.attr_set.subset_of:
            self._get_real_attr().set_reply()

    def get_limit(self, limit, default=None):
        value = self.checks.get(limit, default)
        if value is None:
            return value
        if isinstance(value, int):
            return value
        if value in self.family.consts:
            return self.family.consts[value]["value"]
        return limit_to_number(value)

    def get_limit_str(self, limit, default=None, suffix=''):
        value = self.checks.get(limit, default)
        if value is None:
            return ''
        if isinstance(value, int):
            return str(value) + suffix
        if value in self.family.consts:
            const = self.family.consts[value]
            if const.get('header'):
                return c_upper(value)
            return c_upper(f"{self.family['name']}-{value}")
        return c_upper(value)

    def resolve(self):
        if 'parent-sub-message' in self.attr:
            enum_name = self.attr['parent-sub-message'].enum_name
        elif 'name-prefix' in self.attr:
            enum_name = f"{self.attr['name-prefix']}{self.name}"
        else:
            enum_name = f"{self.attr_set.name_prefix}{self.name}"
        self.enum_name = c_upper(enum_name)

        if self.attr_set.subset_of:
            if self.checks != self._get_real_attr().checks:
                raise Exception("Overriding checks not supported by codegen, yet")

    def is_multi_val(self):
        return None

    def is_scalar(self):
        return self.type in {'u8', 'u16', 'u32', 'u64', 's32', 's64'}

    def is_recursive(self):
        return False

    def is_recursive_for_op(self, ri):
        return self.is_recursive() and not ri.op

    def presence_type(self):
        return 'present'

    def presence_member(self, space, type_filter):
        if self.presence_type() != type_filter:
            return

        if self.presence_type() == 'present':
            pfx = '__' if space == 'user' else ''
            return f"{pfx}u32 {self.c_name}:1;"

        if self.presence_type() in {'len', 'count'}:
            pfx = '__' if space == 'user' else ''
            return f"{pfx}u32 {self.c_name};"

    def _complex_member_type(self, ri):
        return None

    def free_needs_iter(self):
        return False

    def _free_lines(self, ri, var, ref):
        if self.is_multi_val() or self.presence_type() in {'count', 'len'}:
            return [f'free({var}->{ref}{self.c_name});']
        return []

    def free(self, ri, var, ref):
        lines = self._free_lines(ri, var, ref)
        for line in lines:
            ri.cw.p(line)

    def arg_member(self, ri):
        member = self._complex_member_type(ri)
        if member:
            spc = ' ' if member[-1] != '*' else ''
            arg = [member + spc + '*' + self.c_name]
            if self.presence_type() == 'count':
                arg += ['unsigned int n_' + self.c_name]
            return arg
        raise Exception(f"Struct member not implemented for class type {self.type}")

    def struct_member(self, ri):
        member = self._complex_member_type(ri)
        if member:
            ptr = '*' if self.is_multi_val() else ''
            if self.is_recursive_for_op(ri):
                ptr = '*'
            spc = ' ' if member[-1] != '*' else ''
            ri.cw.p(f"{member}{spc}{ptr}{self.c_name};")
            return
        members = self.arg_member(ri)
        for one in members:
            ri.cw.p(one + ';')

    def _attr_policy(self, policy):
        return '{ .type = ' + policy + ', }'

    def attr_policy(self, cw):
        policy = f'NLA_{c_upper(self.type)}'
        if self.attr.get('byte-order') == 'big-endian':
            if self.type in {'u16', 'u32'}:
                policy = f'NLA_BE{self.type[1:]}'

        spec = self._attr_policy(policy)
        cw.p(f"\t[{self.enum_name}] = {spec},")

    def _attr_typol(self):
        raise Exception(f"Type policy not implemented for class type {self.type}")

    def attr_typol(self, cw):
        typol = self._attr_typol()
        cw.p(f'[{self.enum_name}] = {"{"} .name = "{self.name}", {typol}{"}"},')

    def _attr_put_line(self, ri, var, line):
        presence = self.presence_type()
        if presence in {'present', 'len'}:
            ri.cw.p(f"if ({var}->_{presence}.{self.c_name})")
        ri.cw.p(f"{line};")

    def _attr_put_simple(self, ri, var, put_type):
        line = f"ynl_attr_put_{put_type}(nlh, {self.enum_name}, {var}->{self.c_name})"
        self._attr_put_line(ri, var, line)

    def attr_put(self, ri, var):
        raise Exception(f"Put not implemented for class type {self.type}")

    def _attr_get(self, ri, var):
        raise Exception(f"Attr get not implemented for class type {self.type}")

    def attr_get(self, ri, var, first):
        lines, init_lines, local_vars = self._attr_get(ri, var)
        if type(lines) is str:
            lines = [lines]
        if type(init_lines) is str:
            init_lines = [init_lines]

        kw = 'if' if first else 'else if'
        ri.cw.block_start(line=f"{kw} (type == {self.enum_name})")
        if local_vars:
            for local in local_vars:
                ri.cw.p(local)
            ri.cw.nl()

        if not self.is_multi_val():
            ri.cw.p("if (ynl_attr_validate(yarg, attr))")
            ri.cw.p("return YNL_PARSE_CB_ERROR;")
            if self.presence_type() == 'present':
                ri.cw.p(f"{var}->_present.{self.c_name} = 1;")

        if init_lines:
            ri.cw.nl()
            for line in init_lines:
                ri.cw.p(line)

        for line in lines:
            ri.cw.p(line)
        ri.cw.block_end()
        return True

    def _setter_lines(self, ri, member, presence):
        raise Exception(f"Setter not implemented for class type {self.type}")

    def setter(self, ri, space, direction, deref=False, ref=None, var="req"):
        ref = (ref if ref else []) + [self.c_name]
        member = f"{var}->{'.'.join(ref)}"

        local_vars = []
        if self.free_needs_iter():
            local_vars += ['unsigned int i;']

        code = []
        presence = ''
        for i in range(0, len(ref)):
            presence = f"{var}->{'.'.join(ref[:i] + [''])}_present.{ref[i]}"
            # Every layer below last is a nest, so we know it uses bit presence
            # last layer is "self" and may be a complex type
            if i == len(ref) - 1 and self.presence_type() != 'present':
                presence = f"{var}->{'.'.join(ref[:i] + [''])}_{self.presence_type()}.{ref[i]}"
                continue
            code.append(presence + ' = 1;')
        ref_path = '.'.join(ref[:-1])
        if ref_path:
            ref_path += '.'
        code += self._free_lines(ri, var, ref_path)
        code += self._setter_lines(ri, member, presence)

        func_name = f"{op_prefix(ri, direction, deref=deref)}_set_{'_'.join(ref)}"
        free = bool([x for x in code if 'free(' in x])
        alloc = bool([x for x in code if 'alloc(' in x])
        if free and not alloc:
            func_name = '__' + func_name
        ri.cw.write_func('static inline void', func_name, local_vars=local_vars,
                         body=code,
                         args=[f'{type_name(ri, direction, deref=deref)} *{var}'] + self.arg_member(ri))


class TypeUnused(Type):
    def presence_type(self):
        return ''

    def arg_member(self, ri):
        return []

    def _attr_get(self, ri, var):
        return ['return YNL_PARSE_CB_ERROR;'], None, None

    def _attr_typol(self):
        return '.type = YNL_PT_REJECT, '

    def attr_policy(self, cw):
        pass

    def attr_put(self, ri, var):
        pass

    def attr_get(self, ri, var, first):
        pass

    def setter(self, ri, space, direction, deref=False, ref=None, var=None):
        pass


class TypePad(Type):
    def presence_type(self):
        return ''

    def arg_member(self, ri):
        return []

    def _attr_typol(self):
        return '.type = YNL_PT_IGNORE, '

    def attr_put(self, ri, var):
        pass

    def attr_get(self, ri, var, first):
        pass

    def attr_policy(self, cw):
        pass

    def setter(self, ri, space, direction, deref=False, ref=None, var=None):
        pass


class TypeScalar(Type):
    def __init__(self, family, attr_set, attr, value):
        super().__init__(family, attr_set, attr, value)

        self.byte_order_comment = ''
        if 'byte-order' in attr:
            self.byte_order_comment = f" /* {attr['byte-order']} */"

        # Classic families have some funny enums, don't bother
        # computing checks, since we only need them for kernel policies
        if not family.is_classic():
            self._init_checks()

        # Added by resolve():
        self.is_bitfield = None
        delattr(self, "is_bitfield")
        self.type_name = None
        delattr(self, "type_name")

    def resolve(self):
        self.resolve_up(super())

        if 'enum-as-flags' in self.attr and self.attr['enum-as-flags']:
            self.is_bitfield = True
        elif 'enum' in self.attr:
            self.is_bitfield = self.family.consts[self.attr['enum']]['type'] == 'flags'
        else:
            self.is_bitfield = False

        if not self.is_bitfield and 'enum' in self.attr:
            self.type_name = self.family.consts[self.attr['enum']].user_type
        elif self.is_auto_scalar:
            self.type_name = '__' + self.type[0] + '64'
        else:
            self.type_name = '__' + self.type

    def _init_checks(self):
        if 'enum' in self.attr:
            enum = self.family.consts[self.attr['enum']]
            low, high = enum.value_range()
            if low == None and high == None:
                self.checks['sparse'] = True
            else:
                if 'min' not in self.checks:
                    if low != 0 or self.type[0] == 's':
                        self.checks['min'] = low
                if 'max' not in self.checks:
                    self.checks['max'] = high

        if 'min' in self.checks and 'max' in self.checks:
            if self.get_limit('min') > self.get_limit('max'):
                raise Exception(f'Invalid limit for "{self.name}" min: {self.get_limit("min")} max: {self.get_limit("max")}')
            self.checks['range'] = True

        low = min(self.get_limit('min', 0), self.get_limit('max', 0))
        high = max(self.get_limit('min', 0), self.get_limit('max', 0))
        if low < 0 and self.type[0] == 'u':
            raise Exception(f'Invalid limit for "{self.name}" negative limit for unsigned type')
        if low < -32768 or high > 32767:
            self.checks['full-range'] = True

    def _attr_policy(self, policy):
        if 'flags-mask' in self.checks or self.is_bitfield:
            if self.is_bitfield:
                enum = self.family.consts[self.attr['enum']]
                mask = enum.get_mask(as_flags=True)
            else:
                flags = self.family.consts[self.checks['flags-mask']]
                flag_cnt = len(flags['entries'])
                mask = (1 << flag_cnt) - 1
            return f"NLA_POLICY_MASK({policy}, 0x{mask:x})"
        elif 'full-range' in self.checks:
            return f"NLA_POLICY_FULL_RANGE({policy}, &{c_lower(self.enum_name)}_range)"
        elif 'range' in self.checks:
            return f"NLA_POLICY_RANGE({policy}, {self.get_limit_str('min')}, {self.get_limit_str('max')})"
        elif 'min' in self.checks:
            return f"NLA_POLICY_MIN({policy}, {self.get_limit_str('min')})"
        elif 'max' in self.checks:
            return f"NLA_POLICY_MAX({policy}, {self.get_limit_str('max')})"
        elif 'sparse' in self.checks:
            return f"NLA_POLICY_VALIDATE_FN({policy}, &{c_lower(self.enum_name)}_validate)"
        return super()._attr_policy(policy)

    def _attr_typol(self):
        return f'.type = YNL_PT_U{c_upper(self.type[1:])}, '

    def arg_member(self, ri):
        return [f'{self.type_name} {self.c_name}{self.byte_order_comment}']

    def attr_put(self, ri, var):
        self._attr_put_simple(ri, var, self.type)

    def _attr_get(self, ri, var):
        return f"{var}->{self.c_name} = ynl_attr_get_{self.type}(attr);", None, None

    def _setter_lines(self, ri, member, presence):
        return [f"{member} = {self.c_name};"]


class TypeFlag(Type):
    def arg_member(self, ri):
        return []

    def _attr_typol(self):
        return '.type = YNL_PT_FLAG, '

    def attr_put(self, ri, var):
        self._attr_put_line(ri, var, f"ynl_attr_put(nlh, {self.enum_name}, NULL, 0)")

    def _attr_get(self, ri, var):
        return [], None, None

    def _setter_lines(self, ri, member, presence):
        return []


class TypeString(Type):
    def arg_member(self, ri):
        return [f"const char *{self.c_name}"]

    def presence_type(self):
        return 'len'

    def struct_member(self, ri):
        ri.cw.p(f"char *{self.c_name};")

    def _attr_typol(self):
        typol = f'.type = YNL_PT_NUL_STR, '
        if self.is_selector:
            typol += '.is_selector = 1, '
        return typol

    def _attr_policy(self, policy):
        if 'exact-len' in self.checks:
            mem = 'NLA_POLICY_EXACT_LEN(' + self.get_limit_str('exact-len') + ')'
        else:
            mem = '{ .type = ' + policy
            if 'max-len' in self.checks:
                mem += ', .len = ' + self.get_limit_str('max-len')
            mem += ', }'
        return mem

    def attr_policy(self, cw):
        if self.checks.get('unterminated-ok', False):
            policy = 'NLA_STRING'
        else:
            policy = 'NLA_NUL_STRING'

        spec = self._attr_policy(policy)
        cw.p(f"\t[{self.enum_name}] = {spec},")

    def attr_put(self, ri, var):
        self._attr_put_simple(ri, var, 'str')

    def _attr_get(self, ri, var):
        len_mem = var + '->_len.' + self.c_name
        return [f"{len_mem} = len;",
                f"{var}->{self.c_name} = malloc(len + 1);",
                f"memcpy({var}->{self.c_name}, ynl_attr_get_str(attr), len);",
                f"{var}->{self.c_name}[len] = 0;"], \
               ['len = strnlen(ynl_attr_get_str(attr), ynl_attr_data_len(attr));'], \
               ['unsigned int len;']

    def _setter_lines(self, ri, member, presence):
        return [f"{presence} = strlen({self.c_name});",
                f"{member} = malloc({presence} + 1);",
                f'memcpy({member}, {self.c_name}, {presence});',
                f'{member}[{presence}] = 0;']


class TypeBinary(Type):
    def arg_member(self, ri):
        return [f"const void *{self.c_name}", 'size_t len']

    def presence_type(self):
        return 'len'

    def struct_member(self, ri):
        ri.cw.p(f"void *{self.c_name};")

    def _attr_typol(self):
        return f'.type = YNL_PT_BINARY,'

    def _attr_policy(self, policy):
        if len(self.checks) == 0:
            pass
        elif len(self.checks) == 1:
            check_name = list(self.checks)[0]
            if check_name not in {'exact-len', 'min-len', 'max-len'}:
                raise Exception('Unsupported check for binary type: ' + check_name)
        else:
            raise Exception('More than one check for binary type not implemented, yet')

        if len(self.checks) == 0:
            mem = '{ .type = NLA_BINARY, }'
        elif 'exact-len' in self.checks:
            mem = 'NLA_POLICY_EXACT_LEN(' + self.get_limit_str('exact-len') + ')'
        elif 'min-len' in self.checks:
            mem = '{ .len = ' + self.get_limit_str('min-len') + ', }'
        elif 'max-len' in self.checks:
            mem = 'NLA_POLICY_MAX_LEN(' + self.get_limit_str('max-len') + ')'

        return mem

    def attr_put(self, ri, var):
        self._attr_put_line(ri, var, f"ynl_attr_put(nlh, {self.enum_name}, " +
                            f"{var}->{self.c_name}, {var}->_len.{self.c_name})")

    def _attr_get(self, ri, var):
        len_mem = var + '->_len.' + self.c_name
        return [f"{len_mem} = len;",
                f"{var}->{self.c_name} = malloc(len);",
                f"memcpy({var}->{self.c_name}, ynl_attr_data(attr), len);"], \
               ['len = ynl_attr_data_len(attr);'], \
               ['unsigned int len;']

    def _setter_lines(self, ri, member, presence):
        return [f"{presence} = len;",
                f"{member} = malloc({presence});",
                f'memcpy({member}, {self.c_name}, {presence});']


class TypeBinaryStruct(TypeBinary):
    def struct_member(self, ri):
        ri.cw.p(f'struct {c_lower(self.get("struct"))} *{self.c_name};')

    def _attr_get(self, ri, var):
        struct_sz = 'sizeof(struct ' + c_lower(self.get("struct")) + ')'
        len_mem = var + '->_' + self.presence_type() + '.' + self.c_name
        return [f"{len_mem} = len;",
                f"if (len < {struct_sz})",
                f"{var}->{self.c_name} = calloc(1, {struct_sz});",
                "else",
                f"{var}->{self.c_name} = malloc(len);",
                f"memcpy({var}->{self.c_name}, ynl_attr_data(attr), len);"], \
               ['len = ynl_attr_data_len(attr);'], \
               ['unsigned int len;']


class TypeBinaryScalarArray(TypeBinary):
    def arg_member(self, ri):
        return [f'__{self.get("sub-type")} *{self.c_name}', 'size_t count']

    def presence_type(self):
        return 'count'

    def struct_member(self, ri):
        ri.cw.p(f'__{self.get("sub-type")} *{self.c_name};')

    def attr_put(self, ri, var):
        presence = self.presence_type()
        ri.cw.block_start(line=f"if ({var}->_{presence}.{self.c_name})")
        ri.cw.p(f"i = {var}->_{presence}.{self.c_name} * sizeof(__{self.get('sub-type')});")
        ri.cw.p(f"ynl_attr_put(nlh, {self.enum_name}, " +
                f"{var}->{self.c_name}, i);")
        ri.cw.block_end()

    def _attr_get(self, ri, var):
        len_mem = var + '->_count.' + self.c_name
        return [f"{len_mem} = len / sizeof(__{self.get('sub-type')});",
                f"len = {len_mem} * sizeof(__{self.get('sub-type')});",
                f"{var}->{self.c_name} = malloc(len);",
                f"memcpy({var}->{self.c_name}, ynl_attr_data(attr), len);"], \
               ['len = ynl_attr_data_len(attr);'], \
               ['unsigned int len;']

    def _setter_lines(self, ri, member, presence):
        return [f"{presence} = count;",
                f"count *= sizeof(__{self.get('sub-type')});",
                f"{member} = malloc(count);",
                f'memcpy({member}, {self.c_name}, count);']


class TypeBitfield32(Type):
    def _complex_member_type(self, ri):
        return "struct nla_bitfield32"

    def _attr_typol(self):
        return f'.type = YNL_PT_BITFIELD32, '

    def _attr_policy(self, policy):
        if not 'enum' in self.attr:
            raise Exception('Enum required for bitfield32 attr')
        enum = self.family.consts[self.attr['enum']]
        mask = enum.get_mask(as_flags=True)
        return f"NLA_POLICY_BITFIELD32({mask})"

    def attr_put(self, ri, var):
        line = f"ynl_attr_put(nlh, {self.enum_name}, &{var}->{self.c_name}, sizeof(struct nla_bitfield32))"
        self._attr_put_line(ri, var, line)

    def _attr_get(self, ri, var):
        return f"memcpy(&{var}->{self.c_name}, ynl_attr_data(attr), sizeof(struct nla_bitfield32));", None, None

    def _setter_lines(self, ri, member, presence):
        return [f"memcpy(&{member}, {self.c_name}, sizeof(struct nla_bitfield32));"]


class TypeNest(Type):
    def is_recursive(self):
        return self.family.pure_nested_structs[self.nested_attrs].recursive

    def _complex_member_type(self, ri):
        return self.nested_struct_type

    def _free_lines(self, ri, var, ref):
        lines = []
        at = '&'
        if self.is_recursive_for_op(ri):
            at = ''
            lines += [f'if ({var}->{ref}{self.c_name})']
        lines += [f'{self.nested_render_name}_free({at}{var}->{ref}{self.c_name});']
        return lines

    def _attr_typol(self):
        return f'.type = YNL_PT_NEST, .nest = &{self.nested_render_name}_nest, '

    def _attr_policy(self, policy):
        return 'NLA_POLICY_NESTED(' + self.nested_render_name + '_nl_policy)'

    def attr_put(self, ri, var):
        at = '' if self.is_recursive_for_op(ri) else '&'
        self._attr_put_line(ri, var, f"{self.nested_render_name}_put(nlh, " +
                            f"{self.enum_name}, {at}{var}->{self.c_name})")

    def _attr_get(self, ri, var):
        pns = self.family.pure_nested_structs[self.nested_attrs]
        args = ["&parg", "attr"]
        for sel in pns.external_selectors():
            args.append(f'{var}->{sel.name}')
        get_lines = [f"if ({self.nested_render_name}_parse({', '.join(args)}))",
                     "return YNL_PARSE_CB_ERROR;"]
        init_lines = [f"parg.rsp_policy = &{self.nested_render_name}_nest;",
                      f"parg.data = &{var}->{self.c_name};"]
        return get_lines, init_lines, None

    def setter(self, ri, space, direction, deref=False, ref=None, var="req"):
        ref = (ref if ref else []) + [self.c_name]

        for _, attr in ri.family.pure_nested_structs[self.nested_attrs].member_list():
            if attr.is_recursive():
                continue
            attr.setter(ri, self.nested_attrs, direction, deref=deref, ref=ref,
                        var=var)


class TypeMultiAttr(Type):
    def __init__(self, family, attr_set, attr, value, base_type):
        super().__init__(family, attr_set, attr, value)

        self.base_type = base_type

    def is_multi_val(self):
        return True

    def presence_type(self):
        return 'count'

    def _complex_member_type(self, ri):
        if 'type' not in self.attr or self.attr['type'] == 'nest':
            return self.nested_struct_type
        elif self.attr['type'] == 'binary' and 'struct' in self.attr:
            return None  # use arg_member()
        elif self.attr['type'] == 'string':
            return 'struct ynl_string *'
        elif self.attr['type'] in scalars:
            scalar_pfx = '__' if ri.ku_space == 'user' else ''
            return scalar_pfx + self.attr['type']
        else:
            raise Exception(f"Sub-type {self.attr['type']} not supported yet")

    def arg_member(self, ri):
        if self.type == 'binary' and 'struct' in self.attr:
            return [f'struct {c_lower(self.attr["struct"])} *{self.c_name}',
                    f'unsigned int n_{self.c_name}']
        return super().arg_member(ri)

    def free_needs_iter(self):
        return self.attr['type'] in {'nest', 'string'}

    def _free_lines(self, ri, var, ref):
        lines = []
        if self.attr['type'] in scalars:
            lines += [f"free({var}->{ref}{self.c_name});"]
        elif self.attr['type'] == 'binary':
            lines += [f"free({var}->{ref}{self.c_name});"]
        elif self.attr['type'] == 'string':
            lines += [
                f"for (i = 0; i < {var}->{ref}_count.{self.c_name}; i++)",
                f"free({var}->{ref}{self.c_name}[i]);",
                f"free({var}->{ref}{self.c_name});",
            ]
        elif 'type' not in self.attr or self.attr['type'] == 'nest':
            lines += [
                f"for (i = 0; i < {var}->{ref}_count.{self.c_name}; i++)",
                f'{self.nested_render_name}_free(&{var}->{ref}{self.c_name}[i]);',
                f"free({var}->{ref}{self.c_name});",
            ]
        else:
            raise Exception(f"Free of MultiAttr sub-type {self.attr['type']} not supported yet")
        return lines

    def _attr_policy(self, policy):
        return self.base_type._attr_policy(policy)

    def _attr_typol(self):
        return self.base_type._attr_typol()

    def _attr_get(self, ri, var):
        return f'n_{self.c_name}++;', None, None

    def attr_put(self, ri, var):
        if self.attr['type'] in scalars:
            put_type = self.type
            ri.cw.p(f"for (i = 0; i < {var}->_count.{self.c_name}; i++)")
            ri.cw.p(f"ynl_attr_put_{put_type}(nlh, {self.enum_name}, {var}->{self.c_name}[i]);")
        elif self.attr['type'] == 'binary' and 'struct' in self.attr:
            ri.cw.p(f"for (i = 0; i < {var}->_count.{self.c_name}; i++)")
            ri.cw.p(f"ynl_attr_put(nlh, {self.enum_name}, &{var}->{self.c_name}[i], sizeof(struct {c_lower(self.attr['struct'])}));")
        elif self.attr['type'] == 'string':
            ri.cw.p(f"for (i = 0; i < {var}->_count.{self.c_name}; i++)")
            ri.cw.p(f"ynl_attr_put_str(nlh, {self.enum_name}, {var}->{self.c_name}[i]->str);")
        elif 'type' not in self.attr or self.attr['type'] == 'nest':
            ri.cw.p(f"for (i = 0; i < {var}->_count.{self.c_name}; i++)")
            self._attr_put_line(ri, var, f"{self.nested_render_name}_put(nlh, " +
                                f"{self.enum_name}, &{var}->{self.c_name}[i])")
        else:
            raise Exception(f"Put of MultiAttr sub-type {self.attr['type']} not supported yet")

    def _setter_lines(self, ri, member, presence):
        return [f"{member} = {self.c_name};",
                f"{presence} = n_{self.c_name};"]


class TypeArrayNest(Type):
    def is_multi_val(self):
        return True

    def presence_type(self):
        return 'count'

    def _complex_member_type(self, ri):
        if 'sub-type' not in self.attr or self.attr['sub-type'] == 'nest':
            return self.nested_struct_type
        elif self.attr['sub-type'] in scalars:
            scalar_pfx = '__' if ri.ku_space == 'user' else ''
            return scalar_pfx + self.attr['sub-type']
        elif self.attr['sub-type'] == 'binary' and 'exact-len' in self.checks:
            return None  # use arg_member()
        else:
            raise Exception(f"Sub-type {self.attr['sub-type']} not supported yet")

    def arg_member(self, ri):
        if self.sub_type == 'binary' and 'exact-len' in self.checks:
            return [f'unsigned char (*{self.c_name})[{self.checks["exact-len"]}]',
                    f'unsigned int n_{self.c_name}']
        return super().arg_member(ri)

    def _attr_typol(self):
        if self.attr['sub-type'] in scalars:
            return f'.type = YNL_PT_U{c_upper(self.sub_type[1:])}, '
        elif self.attr['sub-type'] == 'binary' and 'exact-len' in self.checks:
            return f'.type = YNL_PT_BINARY, .len = {self.checks["exact-len"]}, '
        else:
            return f'.type = YNL_PT_NEST, .nest = &{self.nested_render_name}_nest, '

    def _attr_get(self, ri, var):
        local_vars = ['const struct nlattr *attr2;']
        get_lines = [f'attr_{self.c_name} = attr;',
                     'ynl_attr_for_each_nested(attr2, attr) {',
                     '\tif (ynl_attr_validate(yarg, attr2))',
                     '\t\treturn YNL_PARSE_CB_ERROR;',
                     f'\t{var}->_count.{self.c_name}++;',
                     '}']
        return get_lines, None, local_vars

    def attr_put(self, ri, var):
        ri.cw.p(f'array = ynl_attr_nest_start(nlh, {self.enum_name});')
        if self.sub_type in scalars:
            put_type = self.sub_type
            ri.cw.block_start(line=f'for (i = 0; i < {var}->_count.{self.c_name}; i++)')
            ri.cw.p(f"ynl_attr_put_{put_type}(nlh, i, {var}->{self.c_name}[i]);")
            ri.cw.block_end()
        elif self.sub_type == 'binary' and 'exact-len' in self.checks:
            ri.cw.p(f'for (i = 0; i < {var}->_count.{self.c_name}; i++)')
            ri.cw.p(f"ynl_attr_put(nlh, i, {var}->{self.c_name}[i], {self.checks['exact-len']});")
        elif self.sub_type == 'nest':
            ri.cw.p(f'for (i = 0; i < {var}->_count.{self.c_name}; i++)')
            ri.cw.p(f"{self.nested_render_name}_put(nlh, i, &{var}->{self.c_name}[i]);")
        else:
            raise Exception(f"Put for ArrayNest sub-type {self.attr['sub-type']} not supported, yet")
        ri.cw.p('ynl_attr_nest_end(nlh, array);')

    def _setter_lines(self, ri, member, presence):
        return [f"{member} = {self.c_name};",
                f"{presence} = n_{self.c_name};"]


class TypeNestTypeValue(Type):
    def _complex_member_type(self, ri):
        return self.nested_struct_type

    def _attr_typol(self):
        return f'.type = YNL_PT_NEST, .nest = &{self.nested_render_name}_nest, '

    def _attr_get(self, ri, var):
        prev = 'attr'
        tv_args = ''
        get_lines = []
        local_vars = []
        init_lines = [f"parg.rsp_policy = &{self.nested_render_name}_nest;",
                      f"parg.data = &{var}->{self.c_name};"]
        if 'type-value' in self.attr:
            tv_names = [c_lower(x) for x in self.attr["type-value"]]
            local_vars += [f'const struct nlattr *attr_{", *attr_".join(tv_names)};']
            local_vars += [f'__u32 {", ".join(tv_names)};']
            for level in self.attr["type-value"]:
                level = c_lower(level)
                get_lines += [f'attr_{level} = ynl_attr_data({prev});']
                get_lines += [f'{level} = ynl_attr_type(attr_{level});']
                prev = 'attr_' + level

            tv_args = f", {', '.join(tv_names)}"

        get_lines += [f"{self.nested_render_name}_parse(&parg, {prev}{tv_args});"]
        return get_lines, init_lines, local_vars


class TypeSubMessage(TypeNest):
    def __init__(self, family, attr_set, attr, value):
        super().__init__(family, attr_set, attr, value)

        self.selector = Selector(attr, attr_set)

    def _attr_typol(self):
        typol = f'.type = YNL_PT_NEST, .nest = &{self.nested_render_name}_nest, '
        typol += '.is_submsg = 1, '
        # Reverse-parsing of the policy (ynl_err_walk() in ynl.c) does not
        # support external selectors. No family uses sub-messages with external
        # selector for requests so this is fine for now.
        if not self.selector.is_external():
            typol += f'.selector_type = {self.attr_set[self["selector"]].value} '
        return typol

    def _attr_get(self, ri, var):
        sel = c_lower(self['selector'])
        if self.selector.is_external():
            sel_var = f"_sel_{sel}"
        else:
            sel_var = f"{var}->{sel}"
        get_lines = [f'if (!{sel_var})',
                     f'return ynl_submsg_failed(yarg, "%s", "%s");' %
                        (self.name, self['selector']),
                    f"if ({self.nested_render_name}_parse(&parg, {sel_var}, attr))",
                     "return YNL_PARSE_CB_ERROR;"]
        init_lines = [f"parg.rsp_policy = &{self.nested_render_name}_nest;",
                      f"parg.data = &{var}->{self.c_name};"]
        return get_lines, init_lines, None


class Selector:
    def __init__(self, msg_attr, attr_set):
        self.name = msg_attr["selector"]

        if self.name in attr_set:
            self.attr = attr_set[self.name]
            self.attr.is_selector = True
            self._external = False
        else:
            # The selector will need to get passed down thru the structs
            self.attr = None
            self._external = True

    def set_attr(self, attr):
        self.attr = attr

    def is_external(self):
        return self._external


class Struct:
    def __init__(self, family, space_name, type_list=None, fixed_header=None,
                 inherited=None, submsg=None):
        self.family = family
        self.space_name = space_name
        self.attr_set = family.attr_sets[space_name]
        # Use list to catch comparisons with empty sets
        self._inherited = inherited if inherited is not None else []
        self.inherited = []
        self.fixed_header = None
        if fixed_header:
            self.fixed_header = 'struct ' + c_lower(fixed_header)
        self.submsg = submsg

        self.nested = type_list is None
        if family.name == c_lower(space_name):
            self.render_name = c_lower(family.ident_name)
        else:
            self.render_name = c_lower(family.ident_name + '-' + space_name)
        self.struct_name = 'struct ' + self.render_name
        if self.nested and space_name in family.consts:
            self.struct_name += '_'
        self.ptr_name = self.struct_name + ' *'
        # All attr sets this one contains, directly or multiple levels down
        self.child_nests = set()

        self.request = False
        self.reply = False
        self.recursive = False
        self.in_multi_val = False  # used by a MultiAttr or and legacy arrays

        self.attr_list = []
        self.attrs = dict()
        if type_list is not None:
            for t in type_list:
                self.attr_list.append((t, self.attr_set[t]),)
        else:
            for t in self.attr_set:
                self.attr_list.append((t, self.attr_set[t]),)

        max_val = 0
        self.attr_max_val = None
        for name, attr in self.attr_list:
            if attr.value >= max_val:
                max_val = attr.value
                self.attr_max_val = attr
            self.attrs[name] = attr

    def __iter__(self):
        yield from self.attrs

    def __getitem__(self, key):
        return self.attrs[key]

    def member_list(self):
        return self.attr_list

    def set_inherited(self, new_inherited):
        if self._inherited != new_inherited:
            raise Exception("Inheriting different members not supported")
        self.inherited = [c_lower(x) for x in sorted(self._inherited)]

    def external_selectors(self):
        sels = []
        for name, attr in self.attr_list:
            if isinstance(attr, TypeSubMessage) and attr.selector.is_external():
                sels.append(attr.selector)
        return sels

    def free_needs_iter(self):
        for _, attr in self.attr_list:
            if attr.free_needs_iter():
                return True
        return False


class EnumEntry(SpecEnumEntry):
    def __init__(self, enum_set, yaml, prev, value_start):
        super().__init__(enum_set, yaml, prev, value_start)

        if prev:
            self.value_change = (self.value != prev.value + 1)
        else:
            self.value_change = (self.value != 0)
        self.value_change = self.value_change or self.enum_set['type'] == 'flags'

        # Added by resolve:
        self.c_name = None
        delattr(self, "c_name")

    def resolve(self):
        self.resolve_up(super())

        self.c_name = c_upper(self.enum_set.value_pfx + self.name)


class EnumSet(SpecEnumSet):
    def __init__(self, family, yaml):
        self.render_name = c_lower(family.ident_name + '-' + yaml['name'])

        if 'enum-name' in yaml:
            if yaml['enum-name']:
                self.enum_name = 'enum ' + c_lower(yaml['enum-name'])
                self.user_type = self.enum_name
            else:
                self.enum_name = None
        else:
            self.enum_name = 'enum ' + self.render_name

        if self.enum_name:
            self.user_type = self.enum_name
        else:
            self.user_type = 'int'

        self.value_pfx = yaml.get('name-prefix', f"{family.ident_name}-{yaml['name']}-")
        self.header = yaml.get('header', None)
        self.enum_cnt_name = yaml.get('enum-cnt-name', None)

        super().__init__(family, yaml)

    def new_entry(self, entry, prev_entry, value_start):
        return EnumEntry(self, entry, prev_entry, value_start)

    def value_range(self):
        low = min([x.value for x in self.entries.values()])
        high = max([x.value for x in self.entries.values()])

        if high - low + 1 != len(self.entries):
            return None, None

        return low, high


class AttrSet(SpecAttrSet):
    def __init__(self, family, yaml):
        super().__init__(family, yaml)

        if self.subset_of is None:
            if 'name-prefix' in yaml:
                pfx = yaml['name-prefix']
            elif self.name == family.name:
                pfx = family.ident_name + '-a-'
            else:
                pfx = f"{family.ident_name}-a-{self.name}-"
            self.name_prefix = c_upper(pfx)
            self.max_name = c_upper(self.yaml.get('attr-max-name', f"{self.name_prefix}max"))
            self.cnt_name = c_upper(self.yaml.get('attr-cnt-name', f"__{self.name_prefix}max"))
        else:
            self.name_prefix = family.attr_sets[self.subset_of].name_prefix
            self.max_name = family.attr_sets[self.subset_of].max_name
            self.cnt_name = family.attr_sets[self.subset_of].cnt_name

        # Added by resolve:
        self.c_name = None
        delattr(self, "c_name")

    def resolve(self):
        self.c_name = c_lower(self.name)
        if self.c_name in _C_KW:
            self.c_name += '_'
        if self.c_name == self.family.c_name:
            self.c_name = ''

    def new_attr(self, elem, value):
        if elem['type'] in scalars:
            t = TypeScalar(self.family, self, elem, value)
        elif elem['type'] == 'unused':
            t = TypeUnused(self.family, self, elem, value)
        elif elem['type'] == 'pad':
            t = TypePad(self.family, self, elem, value)
        elif elem['type'] == 'flag':
            t = TypeFlag(self.family, self, elem, value)
        elif elem['type'] == 'string':
            t = TypeString(self.family, self, elem, value)
        elif elem['type'] == 'binary':
            if 'struct' in elem:
                t = TypeBinaryStruct(self.family, self, elem, value)
            elif elem.get('sub-type') in scalars:
                t = TypeBinaryScalarArray(self.family, self, elem, value)
            else:
                t = TypeBinary(self.family, self, elem, value)
        elif elem['type'] == 'bitfield32':
            t = TypeBitfield32(self.family, self, elem, value)
        elif elem['type'] == 'nest':
            t = TypeNest(self.family, self, elem, value)
        elif elem['type'] == 'indexed-array' and 'sub-type' in elem:
            if elem["sub-type"] in ['binary', 'nest', 'u32']:
                t = TypeArrayNest(self.family, self, elem, value)
            else:
                raise Exception(f'new_attr: unsupported sub-type {elem["sub-type"]}')
        elif elem['type'] == 'nest-type-value':
            t = TypeNestTypeValue(self.family, self, elem, value)
        elif elem['type'] == 'sub-message':
            t = TypeSubMessage(self.family, self, elem, value)
        else:
            raise Exception(f"No typed class for type {elem['type']}")

        if 'multi-attr' in elem and elem['multi-attr']:
            t = TypeMultiAttr(self.family, self, elem, value, t)

        return t


class Operation(SpecOperation):
    def __init__(self, family, yaml, req_value, rsp_value):
        # Fill in missing operation properties (for fixed hdr-only msgs)
        for mode in ['do', 'dump', 'event']:
            for direction in ['request', 'reply']:
                try:
                    yaml[mode][direction].setdefault('attributes', [])
                except KeyError:
                    pass

        super().__init__(family, yaml, req_value, rsp_value)

        self.render_name = c_lower(family.ident_name + '_' + self.name)

        self.dual_policy = ('do' in yaml and 'request' in yaml['do']) and \
                         ('dump' in yaml and 'request' in yaml['dump'])

        self.has_ntf = False

        # Added by resolve:
        self.enum_name = None
        delattr(self, "enum_name")

    def resolve(self):
        self.resolve_up(super())

        if not self.is_async:
            self.enum_name = self.family.op_prefix + c_upper(self.name)
        else:
            self.enum_name = self.family.async_op_prefix + c_upper(self.name)

    def mark_has_ntf(self):
        self.has_ntf = True


class SubMessage(SpecSubMessage):
    def __init__(self, family, yaml):
        super().__init__(family, yaml)

        self.render_name = c_lower(family.ident_name + '-' + yaml['name'])

    def resolve(self):
        self.resolve_up(super())


class Family(SpecFamily):
    def __init__(self, file_name, exclude_ops):
        # Added by resolve:
        self.c_name = None
        delattr(self, "c_name")
        self.op_prefix = None
        delattr(self, "op_prefix")
        self.async_op_prefix = None
        delattr(self, "async_op_prefix")
        self.mcgrps = None
        delattr(self, "mcgrps")
        self.consts = None
        delattr(self, "consts")
        self.hooks = None
        delattr(self, "hooks")

        super().__init__(file_name, exclude_ops=exclude_ops)

        self.fam_key = c_upper(self.yaml.get('c-family-name', self.yaml["name"] + '_FAMILY_NAME'))
        self.ver_key = c_upper(self.yaml.get('c-version-name', self.yaml["name"] + '_FAMILY_VERSION'))

        if 'definitions' not in self.yaml:
            self.yaml['definitions'] = []

        if 'uapi-header' in self.yaml:
            self.uapi_header = self.yaml['uapi-header']
        else:
            self.uapi_header = f"linux/{self.ident_name}.h"
        if self.uapi_header.startswith("linux/") and self.uapi_header.endswith('.h'):
            self.uapi_header_name = self.uapi_header[6:-2]
        else:
            self.uapi_header_name = self.ident_name

    def resolve(self):
        self.resolve_up(super())

        self.c_name = c_lower(self.ident_name)
        if 'name-prefix' in self.yaml['operations']:
            self.op_prefix = c_upper(self.yaml['operations']['name-prefix'])
        else:
            self.op_prefix = c_upper(self.yaml['name'] + '-cmd-')
        if 'async-prefix' in self.yaml['operations']:
            self.async_op_prefix = c_upper(self.yaml['operations']['async-prefix'])
        else:
            self.async_op_prefix = self.op_prefix

        self.mcgrps = self.yaml.get('mcast-groups', {'list': []})

        self.hooks = dict()
        for when in ['pre', 'post']:
            self.hooks[when] = dict()
            for op_mode in ['do', 'dump']:
                self.hooks[when][op_mode] = dict()
                self.hooks[when][op_mode]['set'] = set()
                self.hooks[when][op_mode]['list'] = []

        # dict space-name -> 'request': set(attrs), 'reply': set(attrs)
        self.root_sets = dict()
        # dict space-name -> Struct
        self.pure_nested_structs = dict()

        self._mark_notify()
        self._mock_up_events()

        self._load_root_sets()
        self._load_nested_sets()
        self._load_attr_use()
        self._load_selector_passing()
        self._load_hooks()

        self.kernel_policy = self.yaml.get('kernel-policy', 'split')
        if self.kernel_policy == 'global':
            self._load_global_policy()

    def new_enum(self, elem):
        return EnumSet(self, elem)

    def new_attr_set(self, elem):
        return AttrSet(self, elem)

    def new_operation(self, elem, req_value, rsp_value):
        return Operation(self, elem, req_value, rsp_value)

    def new_sub_message(self, elem):
        return SubMessage(self, elem)

    def is_classic(self):
        return self.proto == 'netlink-raw'

    def _mark_notify(self):
        for op in self.msgs.values():
            if 'notify' in op:
                self.ops[op['notify']].mark_has_ntf()

    # Fake a 'do' equivalent of all events, so that we can render their response parsing
    def _mock_up_events(self):
        for op in self.yaml['operations']['list']:
            if 'event' in op:
                op['do'] = {
                    'reply': {
                        'attributes': op['event']['attributes']
                    }
                }

    def _load_root_sets(self):
        for op_name, op in self.msgs.items():
            if 'attribute-set' not in op:
                continue

            req_attrs = set()
            rsp_attrs = set()
            for op_mode in ['do', 'dump']:
                if op_mode in op and 'request' in op[op_mode]:
                    req_attrs.update(set(op[op_mode]['request']['attributes']))
                if op_mode in op and 'reply' in op[op_mode]:
                    rsp_attrs.update(set(op[op_mode]['reply']['attributes']))
            if 'event' in op:
                rsp_attrs.update(set(op['event']['attributes']))

            if op['attribute-set'] not in self.root_sets:
                self.root_sets[op['attribute-set']] = {'request': req_attrs, 'reply': rsp_attrs}
            else:
                self.root_sets[op['attribute-set']]['request'].update(req_attrs)
                self.root_sets[op['attribute-set']]['reply'].update(rsp_attrs)

    def _sort_pure_types(self):
        # Try to reorder according to dependencies
        pns_key_list = list(self.pure_nested_structs.keys())
        pns_key_seen = set()
        rounds = len(pns_key_list) ** 2  # it's basically bubble sort
        for _ in range(rounds):
            if len(pns_key_list) == 0:
                break
            name = pns_key_list.pop(0)
            finished = True
            for _, spec in self.attr_sets[name].items():
                if 'nested-attributes' in spec:
                    nested = spec['nested-attributes']
                elif 'sub-message' in spec:
                    nested = spec.sub_message
                else:
                    continue

                # If the unknown nest we hit is recursive it's fine, it'll be a pointer
                if self.pure_nested_structs[nested].recursive:
                    continue
                if nested not in pns_key_seen:
                    # Dicts are sorted, this will make struct last
                    struct = self.pure_nested_structs.pop(name)
                    self.pure_nested_structs[name] = struct
                    finished = False
                    break
            if finished:
                pns_key_seen.add(name)
            else:
                pns_key_list.append(name)

    def _load_nested_set_nest(self, spec):
        inherit = set()
        nested = spec['nested-attributes']
        if nested not in self.root_sets:
            if nested not in self.pure_nested_structs:
                self.pure_nested_structs[nested] = \
                    Struct(self, nested, inherited=inherit,
                           fixed_header=spec.get('fixed-header'))
        else:
            raise Exception(f'Using attr set as root and nested not supported - {nested}')

        if 'type-value' in spec:
            if nested in self.root_sets:
                raise Exception("Inheriting members to a space used as root not supported")
            inherit.update(set(spec['type-value']))
        elif spec['type'] == 'indexed-array':
            inherit.add('idx')
        self.pure_nested_structs[nested].set_inherited(inherit)

        return nested

    def _load_nested_set_submsg(self, spec):
        # Fake the struct type for the sub-message itself
        # its not a attr_set but codegen wants attr_sets.
        submsg = self.sub_msgs[spec["sub-message"]]
        nested = submsg.name

        attrs = []
        for name, fmt in submsg.formats.items():
            attr = {
                "name": name,
                "parent-sub-message": spec,
            }
            if 'attribute-set' in fmt:
                attr |= {
                    "type": "nest",
                    "nested-attributes": fmt['attribute-set'],
                }
                if 'fixed-header' in fmt:
                    attr |= { "fixed-header": fmt["fixed-header"] }
            elif 'fixed-header' in fmt:
                attr |= {
                    "type": "binary",
                    "struct": fmt["fixed-header"],
                }
            else:
                attr["type"] = "flag"
            attrs.append(attr)

        self.attr_sets[nested] = AttrSet(self, {
            "name": nested,
            "name-pfx": self.name + '-' + spec.name + '-',
            "attributes": attrs
        })

        if nested not in self.pure_nested_structs:
            self.pure_nested_structs[nested] = Struct(self, nested, submsg=submsg)

        return nested

    def _load_nested_sets(self):
        attr_set_queue = list(self.root_sets.keys())
        attr_set_seen = set(self.root_sets.keys())

        while len(attr_set_queue):
            a_set = attr_set_queue.pop(0)
            for attr, spec in self.attr_sets[a_set].items():
                if 'nested-attributes' in spec:
                    nested = self._load_nested_set_nest(spec)
                elif 'sub-message' in spec:
                    nested = self._load_nested_set_submsg(spec)
                else:
                    continue

                if nested not in attr_set_seen:
                    attr_set_queue.append(nested)
                    attr_set_seen.add(nested)

        for root_set, rs_members in self.root_sets.items():
            for attr, spec in self.attr_sets[root_set].items():
                if 'nested-attributes' in spec:
                    nested = spec['nested-attributes']
                elif 'sub-message' in spec:
                    nested = spec.sub_message
                else:
                    nested = None

                if nested:
                    if attr in rs_members['request']:
                        self.pure_nested_structs[nested].request = True
                    if attr in rs_members['reply']:
                        self.pure_nested_structs[nested].reply = True

                    if spec.is_multi_val():
                        child = self.pure_nested_structs.get(nested)
                        child.in_multi_val = True

        self._sort_pure_types()

        # Propagate the request / reply / recursive
        for attr_set, struct in reversed(self.pure_nested_structs.items()):
            for _, spec in self.attr_sets[attr_set].items():
                if attr_set in struct.child_nests:
                    struct.recursive = True

                if 'nested-attributes' in spec:
                    child_name = spec['nested-attributes']
                elif 'sub-message' in spec:
                    child_name = spec.sub_message
                else:
                    continue

                struct.child_nests.add(child_name)
                child = self.pure_nested_structs.get(child_name)
                if child:
                    if not child.recursive:
                        struct.child_nests.update(child.child_nests)
                    child.request |= struct.request
                    child.reply |= struct.reply
                    if spec.is_multi_val():
                        child.in_multi_val = True

        self._sort_pure_types()

    def _load_attr_use(self):
        for _, struct in self.pure_nested_structs.items():
            if struct.request:
                for _, arg in struct.member_list():
                    arg.set_request()
            if struct.reply:
                for _, arg in struct.member_list():
                    arg.set_reply()

        for root_set, rs_members in self.root_sets.items():
            for attr, spec in self.attr_sets[root_set].items():
                if attr in rs_members['request']:
                    spec.set_request()
                if attr in rs_members['reply']:
                    spec.set_reply()

    def _load_selector_passing(self):
        def all_structs():
            for k, v in reversed(self.pure_nested_structs.items()):
                yield k, v
            for k, _ in self.root_sets.items():
                yield k, None  # we don't have a struct, but it must be terminal

        for attr_set, struct in all_structs():
            for _, spec in self.attr_sets[attr_set].items():
                if 'nested-attributes' in spec:
                    child_name = spec['nested-attributes']
                elif 'sub-message' in spec:
                    child_name = spec.sub_message
                else:
                    continue

                child = self.pure_nested_structs.get(child_name)
                for selector in child.external_selectors():
                    if selector.name in self.attr_sets[attr_set]:
                        sel_attr = self.attr_sets[attr_set][selector.name]
                        selector.set_attr(sel_attr)
                    else:
                        raise Exception("Passing selector thru more than one layer not supported")

    def _load_global_policy(self):
        global_set = set()
        attr_set_name = None
        for op_name, op in self.ops.items():
            if not op:
                continue
            if 'attribute-set' not in op:
                continue

            if attr_set_name is None:
                attr_set_name = op['attribute-set']
            if attr_set_name != op['attribute-set']:
                raise Exception('For a global policy all ops must use the same set')

            for op_mode in ['do', 'dump']:
                if op_mode in op:
                    req = op[op_mode].get('request')
                    if req:
                        global_set.update(req.get('attributes', []))

        self.global_policy = []
        self.global_policy_set = attr_set_name
        for attr in self.attr_sets[attr_set_name]:
            if attr in global_set:
                self.global_policy.append(attr)

    def _load_hooks(self):
        for op in self.ops.values():
            for op_mode in ['do', 'dump']:
                if op_mode not in op:
                    continue
                for when in ['pre', 'post']:
                    if when not in op[op_mode]:
                        continue
                    name = op[op_mode][when]
                    if name in self.hooks[when][op_mode]['set']:
                        continue
                    self.hooks[when][op_mode]['set'].add(name)
                    self.hooks[when][op_mode]['list'].append(name)


class RenderInfo:
    def __init__(self, cw, family, ku_space, op, op_mode, attr_set=None):
        self.family = family
        self.nl = cw.nlib
        self.ku_space = ku_space
        self.op_mode = op_mode
        self.op = op

        fixed_hdr = op.fixed_header if op else None
        self.fixed_hdr_len = 'ys->family->hdr_len'
        if op and op.fixed_header:
            if op.fixed_header != family.fixed_header:
                if family.is_classic():
                    self.fixed_hdr_len = f"sizeof(struct {c_lower(fixed_hdr)})"
                else:
                    raise Exception(f"Per-op fixed header not supported, yet")


        # 'do' and 'dump' response parsing is identical
        self.type_consistent = True
        self.type_oneside = False
        if op_mode != 'do' and 'dump' in op:
            if 'do' in op:
                if ('reply' in op['do']) != ('reply' in op["dump"]):
                    self.type_consistent = False
                elif 'reply' in op['do'] and op["do"]["reply"] != op["dump"]["reply"]:
                    self.type_consistent = False
            else:
                self.type_consistent = True
                self.type_oneside = True

        self.attr_set = attr_set
        if not self.attr_set:
            self.attr_set = op['attribute-set']

        self.type_name_conflict = False
        if op:
            self.type_name = c_lower(op.name)
        else:
            self.type_name = c_lower(attr_set)
            if attr_set in family.consts:
                self.type_name_conflict = True

        self.cw = cw

        self.struct = dict()
        if op_mode == 'notify':
            op_mode = 'do' if 'do' in op else 'dump'
        for op_dir in ['request', 'reply']:
            if op:
                type_list = []
                if op_dir in op[op_mode]:
                    type_list = op[op_mode][op_dir]['attributes']
                self.struct[op_dir] = Struct(family, self.attr_set,
                                             fixed_header=fixed_hdr,
                                             type_list=type_list)
        if op_mode == 'event':
            self.struct['reply'] = Struct(family, self.attr_set,
                                          fixed_header=fixed_hdr,
                                          type_list=op['event']['attributes'])

    def type_empty(self, key):
        return len(self.struct[key].attr_list) == 0 and \
            self.struct['request'].fixed_header is None

    def needs_nlflags(self, direction):
        return self.op_mode == 'do' and direction == 'request' and self.family.is_classic()


class CodeWriter:
    def __init__(self, nlib, out_file=None, overwrite=True):
        self.nlib = nlib
        self._overwrite = overwrite

        self._nl = False
        self._block_end = False
        self._silent_block = False
        self._ind = 0
        self._ifdef_block = None
        if out_file is None:
            self._out = os.sys.stdout
        else:
            self._out = tempfile.NamedTemporaryFile('w+')
            self._out_file = out_file

    def __del__(self):
        self.close_out_file()

    def close_out_file(self):
        if self._out == os.sys.stdout:
            return
        # Avoid modifying the file if contents didn't change
        self._out.flush()
        if not self._overwrite and os.path.isfile(self._out_file):
            if filecmp.cmp(self._out.name, self._out_file, shallow=False):
                return
        with open(self._out_file, 'w+') as out_file:
            self._out.seek(0)
            shutil.copyfileobj(self._out, out_file)
            self._out.close()
        self._out = os.sys.stdout

    @classmethod
    def _is_cond(cls, line):
        return line.startswith('if') or line.startswith('while') or line.startswith('for')

    def p(self, line, add_ind=0):
        if self._block_end:
            self._block_end = False
            if line.startswith('else'):
                line = '} ' + line
            else:
                self._out.write('\t' * self._ind + '}\n')

        if self._nl:
            self._out.write('\n')
            self._nl = False

        ind = self._ind
        if line[-1] == ':':
            ind -= 1
        if self._silent_block:
            ind += 1
        self._silent_block = line.endswith(')') and CodeWriter._is_cond(line)
        self._silent_block |= line.strip() == 'else'
        if line[0] == '#':
            ind = 0
        if add_ind:
            ind += add_ind
        self._out.write('\t' * ind + line + '\n')

    def nl(self):
        self._nl = True

    def block_start(self, line=''):
        if line:
            line = line + ' '
        self.p(line + '{')
        self._ind += 1

    def block_end(self, line=''):
        if line and line[0] not in {';', ','}:
            line = ' ' + line
        self._ind -= 1
        self._nl = False
        if not line:
            # Delay printing closing bracket in case "else" comes next
            if self._block_end:
                self._out.write('\t' * (self._ind + 1) + '}\n')
            self._block_end = True
        else:
            self.p('}' + line)

    def write_doc_line(self, doc, indent=True):
        words = doc.split()
        line = ' *'
        for word in words:
            if len(line) + len(word) >= 79:
                self.p(line)
                line = ' *'
                if indent:
                    line += '  '
            line += ' ' + word
        self.p(line)

    def write_func_prot(self, qual_ret, name, args=None, doc=None, suffix=''):
        if not args:
            args = ['void']

        if doc:
            self.p('/*')
            self.p(' * ' + doc)
            self.p(' */')

        oneline = qual_ret
        if qual_ret[-1] != '*':
            oneline += ' '
        oneline += f"{name}({', '.join(args)}){suffix}"

        if len(oneline) < 80:
            self.p(oneline)
            return

        v = qual_ret
        if len(v) > 3:
            self.p(v)
            v = ''
        elif qual_ret[-1] != '*':
            v += ' '
        v += name + '('
        ind = '\t' * (len(v) // 8) + ' ' * (len(v) % 8)
        delta_ind = len(v) - len(ind)
        v += args[0]
        i = 1
        while i < len(args):
            next_len = len(v) + len(args[i])
            if v[0] == '\t':
                next_len += delta_ind
            if next_len > 76:
                self.p(v + ',')
                v = ind
            else:
                v += ', '
            v += args[i]
            i += 1
        self.p(v + ')' + suffix)

    def write_func_lvar(self, local_vars):
        if not local_vars:
            return

        if type(local_vars) is str:
            local_vars = [local_vars]

        local_vars.sort(key=len, reverse=True)
        for var in local_vars:
            self.p(var)
        self.nl()

    def write_func(self, qual_ret, name, body, args=None, local_vars=None):
        self.write_func_prot(qual_ret=qual_ret, name=name, args=args)
        self.block_start()
        self.write_func_lvar(local_vars=local_vars)

        for line in body:
            self.p(line)
        self.block_end()

    def writes_defines(self, defines):
        longest = 0
        for define in defines:
            if len(define[0]) > longest:
                longest = len(define[0])
        longest = ((longest + 8) // 8) * 8
        for define in defines:
            line = '#define ' + define[0]
            line += '\t' * ((longest - len(define[0]) + 7) // 8)
            if type(define[1]) is int:
                line += str(define[1])
            elif type(define[1]) is str:
                line += '"' + define[1] + '"'
            self.p(line)

    def write_struct_init(self, members):
        longest = max([len(x[0]) for x in members])
        longest += 1  # because we prepend a .
        longest = ((longest + 8) // 8) * 8
        for one in members:
            line = '.' + one[0]
            line += '\t' * ((longest - len(one[0]) - 1 + 7) // 8)
            line += '= ' + str(one[1]) + ','
            self.p(line)

    def ifdef_block(self, config):
        config_option = None
        if config:
            config_option = 'CONFIG_' + c_upper(config)
        if self._ifdef_block == config_option:
            return

        if self._ifdef_block:
            self.p('#endif /* ' + self._ifdef_block + ' */')
        if config_option:
            self.p('#ifdef ' + config_option)
        self._ifdef_block = config_option


scalars = {'u8', 'u16', 'u32', 'u64', 's8', 's16', 's32', 's64', 'uint', 'sint'}

direction_to_suffix = {
    'reply': '_rsp',
    'request': '_req',
    '': ''
}

op_mode_to_wrapper = {
    'do': '',
    'dump': '_list',
    'notify': '_ntf',
    'event': '',
}

_C_KW = {
    'auto',
    'bool',
    'break',
    'case',
    'char',
    'const',
    'continue',
    'default',
    'do',
    'double',
    'else',
    'enum',
    'extern',
    'float',
    'for',
    'goto',
    'if',
    'inline',
    'int',
    'long',
    'register',
    'return',
    'short',
    'signed',
    'sizeof',
    'static',
    'struct',
    'switch',
    'typedef',
    'union',
    'unsigned',
    'void',
    'volatile',
    'while'
}


def rdir(direction):
    if direction == 'reply':
        return 'request'
    if direction == 'request':
        return 'reply'
    return direction


def op_prefix(ri, direction, deref=False):
    suffix = f"_{ri.type_name}"

    if not ri.op_mode:
        pass
    elif ri.op_mode == 'do':
        suffix += f"{direction_to_suffix[direction]}"
    else:
        if direction == 'request':
            suffix += '_req'
            if not ri.type_oneside:
                suffix += '_dump'
        else:
            if ri.type_consistent:
                if deref:
                    suffix += f"{direction_to_suffix[direction]}"
                else:
                    suffix += op_mode_to_wrapper[ri.op_mode]
            else:
                suffix += '_rsp'
                suffix += '_dump' if deref else '_list'

    return f"{ri.family.c_name}{suffix}"


def type_name(ri, direction, deref=False):
    return f"struct {op_prefix(ri, direction, deref=deref)}"


def print_prototype(ri, direction, terminate=True, doc=None):
    suffix = ';' if terminate else ''

    fname = ri.op.render_name
    if ri.op_mode == 'dump':
        fname += '_dump'

    args = ['struct ynl_sock *ys']
    if 'request' in ri.op[ri.op_mode]:
        args.append(f"{type_name(ri, direction)} *" + f"{direction_to_suffix[direction][1:]}")

    ret = 'int'
    if 'reply' in ri.op[ri.op_mode]:
        ret = f"{type_name(ri, rdir(direction))} *"

    ri.cw.write_func_prot(ret, fname, args, doc=doc, suffix=suffix)


def print_req_prototype(ri):
    print_prototype(ri, "request", doc=ri.op['doc'])


def print_dump_prototype(ri):
    print_prototype(ri, "request")


def put_typol_submsg(cw, struct):
    cw.block_start(line=f'const struct ynl_policy_attr {struct.render_name}_policy[] =')

    i = 0
    for name, arg in struct.member_list():
        nest = ""
        if arg.type == 'nest':
            nest = f" .nest = &{arg.nested_render_name}_nest,"
        cw.p('[%d] = { .type = YNL_PT_SUBMSG, .name = "%s",%s },' %
             (i, name, nest))
        i += 1

    cw.block_end(line=';')
    cw.nl()

    cw.block_start(line=f'const struct ynl_policy_nest {struct.render_name}_nest =')
    cw.p(f'.max_attr = {i - 1},')
    cw.p(f'.table = {struct.render_name}_policy,')
    cw.block_end(line=';')
    cw.nl()


def put_typol_fwd(cw, struct):
    cw.p(f'extern const struct ynl_policy_nest {struct.render_name}_nest;')


def put_typol(cw, struct):
    if struct.submsg:
        put_typol_submsg(cw, struct)
        return

    type_max = struct.attr_set.max_name
    cw.block_start(line=f'const struct ynl_policy_attr {struct.render_name}_policy[{type_max} + 1] =')

    for _, arg in struct.member_list():
        arg.attr_typol(cw)

    cw.block_end(line=';')
    cw.nl()

    cw.block_start(line=f'const struct ynl_policy_nest {struct.render_name}_nest =')
    cw.p(f'.max_attr = {type_max},')
    cw.p(f'.table = {struct.render_name}_policy,')
    cw.block_end(line=';')
    cw.nl()


def _put_enum_to_str_helper(cw, render_name, map_name, arg_name, enum=None):
    args = [f'int {arg_name}']
    if enum:
        args = [enum.user_type + ' ' + arg_name]
    cw.write_func_prot('const char *', f'{render_name}_str', args)
    cw.block_start()
    if enum and enum.type == 'flags':
        cw.p(f'{arg_name} = ffs({arg_name}) - 1;')
    cw.p(f'if ({arg_name} < 0 || {arg_name} >= (int)YNL_ARRAY_SIZE({map_name}))')
    cw.p('return NULL;')
    cw.p(f'return {map_name}[{arg_name}];')
    cw.block_end()
    cw.nl()


def put_op_name_fwd(family, cw):
    cw.write_func_prot('const char *', f'{family.c_name}_op_str', ['int op'], suffix=';')


def put_op_name(family, cw):
    map_name = f'{family.c_name}_op_strmap'
    cw.block_start(line=f"static const char * const {map_name}[] =")
    for op_name, op in family.msgs.items():
        if op.rsp_value:
            # Make sure we don't add duplicated entries, if multiple commands
            # produce the same response in legacy families.
            if family.rsp_by_value[op.rsp_value] != op:
                cw.p(f'// skip "{op_name}", duplicate reply value')
                continue

            if op.req_value == op.rsp_value:
                cw.p(f'[{op.enum_name}] = "{op_name}",')
            else:
                cw.p(f'[{op.rsp_value}] = "{op_name}",')
    cw.block_end(line=';')
    cw.nl()

    _put_enum_to_str_helper(cw, family.c_name + '_op', map_name, 'op')


def put_enum_to_str_fwd(family, cw, enum):
    args = [enum.user_type + ' value']
    cw.write_func_prot('const char *', f'{enum.render_name}_str', args, suffix=';')


def put_enum_to_str(family, cw, enum):
    map_name = f'{enum.render_name}_strmap'
    cw.block_start(line=f"static const char * const {map_name}[] =")
    for entry in enum.entries.values():
        cw.p(f'[{entry.value}] = "{entry.name}",')
    cw.block_end(line=';')
    cw.nl()

    _put_enum_to_str_helper(cw, enum.render_name, map_name, 'value', enum=enum)


def put_req_nested_prototype(ri, struct, suffix=';'):
    func_args = ['struct nlmsghdr *nlh',
                 'unsigned int attr_type',
                 f'{struct.ptr_name}obj']

    ri.cw.write_func_prot('int', f'{struct.render_name}_put', func_args,
                          suffix=suffix)


def put_req_nested(ri, struct):
    local_vars = []
    init_lines = []

    if struct.submsg is None:
        local_vars.append('struct nlattr *nest;')
        init_lines.append("nest = ynl_attr_nest_start(nlh, attr_type);")
    if struct.fixed_header:
        local_vars.append('void *hdr;')
        struct_sz = f'sizeof({struct.fixed_header})'
        init_lines.append(f"hdr = ynl_nlmsg_put_extra_header(nlh, {struct_sz});")
        init_lines.append(f"memcpy(hdr, &obj->_hdr, {struct_sz});")

    has_anest = False
    has_count = False
    for _, arg in struct.member_list():
        has_anest |= arg.type == 'indexed-array'
        has_count |= arg.presence_type() == 'count'
    if has_anest:
        local_vars.append('struct nlattr *array;')
    if has_count:
        local_vars.append('unsigned int i;')

    put_req_nested_prototype(ri, struct, suffix='')
    ri.cw.block_start()
    ri.cw.write_func_lvar(local_vars)

    for line in init_lines:
        ri.cw.p(line)

    for _, arg in struct.member_list():
        arg.attr_put(ri, "obj")

    if struct.submsg is None:
        ri.cw.p("ynl_attr_nest_end(nlh, nest);")

    ri.cw.nl()
    ri.cw.p('return 0;')
    ri.cw.block_end()
    ri.cw.nl()


def _multi_parse(ri, struct, init_lines, local_vars):
    if struct.fixed_header:
        local_vars += ['void *hdr;']
    if struct.nested:
        if struct.fixed_header:
            iter_line = f"ynl_attr_for_each_nested_off(attr, nested, sizeof({struct.fixed_header}))"
        else:
            iter_line = "ynl_attr_for_each_nested(attr, nested)"
    else:
        iter_line = "ynl_attr_for_each(attr, nlh, yarg->ys->family->hdr_len)"
        if ri.op.fixed_header != ri.family.fixed_header:
            if ri.family.is_classic():
                iter_line = f"ynl_attr_for_each(attr, nlh, sizeof({struct.fixed_header}))"
            else:
                raise Exception(f"Per-op fixed header not supported, yet")

    array_nests = set()
    multi_attrs = set()
    needs_parg = False
    for arg, aspec in struct.member_list():
        if aspec['type'] == 'indexed-array' and 'sub-type' in aspec:
            if aspec["sub-type"] in {'binary', 'nest'}:
                local_vars.append(f'const struct nlattr *attr_{aspec.c_name};')
                array_nests.add(arg)
            elif aspec['sub-type'] in scalars:
                local_vars.append(f'const struct nlattr *attr_{aspec.c_name};')
                array_nests.add(arg)
            else:
                raise Exception(f'Not supported sub-type {aspec["sub-type"]}')
        if 'multi-attr' in aspec:
            multi_attrs.add(arg)
        needs_parg |= 'nested-attributes' in aspec
        needs_parg |= 'sub-message' in aspec
    if array_nests or multi_attrs:
        local_vars.append('int i;')
    if needs_parg:
        local_vars.append('struct ynl_parse_arg parg;')
        init_lines.append('parg.ys = yarg->ys;')

    all_multi = array_nests | multi_attrs

    for anest in sorted(all_multi):
        local_vars.append(f"unsigned int n_{struct[anest].c_name} = 0;")

    ri.cw.block_start()
    ri.cw.write_func_lvar(local_vars)

    for line in init_lines:
        ri.cw.p(line)
    ri.cw.nl()

    for arg in struct.inherited:
        ri.cw.p(f'dst->{arg} = {arg};')

    if struct.fixed_header:
        if struct.nested:
            ri.cw.p('hdr = ynl_attr_data(nested);')
        elif ri.family.is_classic():
            ri.cw.p('hdr = ynl_nlmsg_data(nlh);')
        else:
            ri.cw.p('hdr = ynl_nlmsg_data_offset(nlh, sizeof(struct genlmsghdr));')
        ri.cw.p(f"memcpy(&dst->_hdr, hdr, sizeof({struct.fixed_header}));")
    for anest in sorted(all_multi):
        aspec = struct[anest]
        ri.cw.p(f"if (dst->{aspec.c_name})")
        ri.cw.p(f'return ynl_error_parse(yarg, "attribute already present ({struct.attr_set.name}.{aspec.name})");')

    ri.cw.nl()
    ri.cw.block_start(line=iter_line)
    ri.cw.p('unsigned int type = ynl_attr_type(attr);')
    ri.cw.nl()

    first = True
    for _, arg in struct.member_list():
        good = arg.attr_get(ri, 'dst', first=first)
        # First may be 'unused' or 'pad', ignore those
        first &= not good

    ri.cw.block_end()
    ri.cw.nl()

    for anest in sorted(array_nests):
        aspec = struct[anest]

        ri.cw.block_start(line=f"if (n_{aspec.c_name})")
        ri.cw.p(f"dst->{aspec.c_name} = calloc(n_{aspec.c_name}, sizeof(*dst->{aspec.c_name}));")
        ri.cw.p(f"dst->_count.{aspec.c_name} = n_{aspec.c_name};")
        ri.cw.p('i = 0;')
        if 'nested-attributes' in aspec:
            ri.cw.p(f"parg.rsp_policy = &{aspec.nested_render_name}_nest;")
        ri.cw.block_start(line=f"ynl_attr_for_each_nested(attr, attr_{aspec.c_name})")
        if 'nested-attributes' in aspec:
            ri.cw.p(f"parg.data = &dst->{aspec.c_name}[i];")
            ri.cw.p(f"if ({aspec.nested_render_name}_parse(&parg, attr, ynl_attr_type(attr)))")
            ri.cw.p('return YNL_PARSE_CB_ERROR;')
        elif aspec.sub_type in scalars:
            ri.cw.p(f"dst->{aspec.c_name}[i] = ynl_attr_get_{aspec.sub_type}(attr);")
        elif aspec.sub_type == 'binary' and 'exact-len' in aspec.checks:
            # Length is validated by typol
            ri.cw.p(f'memcpy(dst->{aspec.c_name}[i], ynl_attr_data(attr), {aspec.checks["exact-len"]});')
        else:
            raise Exception(f"Nest parsing type not supported in {aspec['name']}")
        ri.cw.p('i++;')
        ri.cw.block_end()
        ri.cw.block_end()
    ri.cw.nl()

    for anest in sorted(multi_attrs):
        aspec = struct[anest]
        ri.cw.block_start(line=f"if (n_{aspec.c_name})")
        ri.cw.p(f"dst->{aspec.c_name} = calloc(n_{aspec.c_name}, sizeof(*dst->{aspec.c_name}));")
        ri.cw.p(f"dst->_count.{aspec.c_name} = n_{aspec.c_name};")
        ri.cw.p('i = 0;')
        if 'nested-attributes' in aspec:
            ri.cw.p(f"parg.rsp_policy = &{aspec.nested_render_name}_nest;")
        ri.cw.block_start(line=iter_line)
        ri.cw.block_start(line=f"if (ynl_attr_type(attr) == {aspec.enum_name})")
        if 'nested-attributes' in aspec:
            ri.cw.p(f"parg.data = &dst->{aspec.c_name}[i];")
            ri.cw.p(f"if ({aspec.nested_render_name}_parse(&parg, attr))")
            ri.cw.p('return YNL_PARSE_CB_ERROR;')
        elif aspec.type in scalars:
            ri.cw.p(f"dst->{aspec.c_name}[i] = ynl_attr_get_{aspec.type}(attr);")
        elif aspec.type == 'binary' and 'struct' in aspec:
            ri.cw.p('size_t len = ynl_attr_data_len(attr);')
            ri.cw.nl()
            ri.cw.p(f'if (len > sizeof(dst->{aspec.c_name}[0]))')
            ri.cw.p(f'len = sizeof(dst->{aspec.c_name}[0]);')
            ri.cw.p(f"memcpy(&dst->{aspec.c_name}[i], ynl_attr_data(attr), len);")
        elif aspec.type == 'string':
            ri.cw.p('unsigned int len;')
            ri.cw.nl()
            ri.cw.p('len = strnlen(ynl_attr_get_str(attr), ynl_attr_data_len(attr));')
            ri.cw.p(f'dst->{aspec.c_name}[i] = malloc(sizeof(struct ynl_string) + len + 1);')
            ri.cw.p(f"dst->{aspec.c_name}[i]->len = len;")
            ri.cw.p(f"memcpy(dst->{aspec.c_name}[i]->str, ynl_attr_get_str(attr), len);")
            ri.cw.p(f"dst->{aspec.c_name}[i]->str[len] = 0;")
        else:
            raise Exception(f'Nest parsing of type {aspec.type} not supported yet')
        ri.cw.p('i++;')
        ri.cw.block_end()
        ri.cw.block_end()
        ri.cw.block_end()
    ri.cw.nl()

    if struct.nested:
        ri.cw.p('return 0;')
    else:
        ri.cw.p('return YNL_PARSE_CB_OK;')
    ri.cw.block_end()
    ri.cw.nl()


def parse_rsp_submsg(ri, struct):
    parse_rsp_nested_prototype(ri, struct, suffix='')

    var = 'dst'
    local_vars = {'const struct nlattr *attr = nested;',
                  f'{struct.ptr_name}{var} = yarg->data;',
                  'struct ynl_parse_arg parg;'}

    for _, arg in struct.member_list():
        _, _, l_vars = arg._attr_get(ri, var)
        local_vars |= set(l_vars) if l_vars else set()

    ri.cw.block_start()
    ri.cw.write_func_lvar(list(local_vars))
    ri.cw.p('parg.ys = yarg->ys;')
    ri.cw.nl()

    first = True
    for name, arg in struct.member_list():
        kw = 'if' if first else 'else if'
        first = False

        ri.cw.block_start(line=f'{kw} (!strcmp(sel, "{name}"))')
        get_lines, init_lines, _ = arg._attr_get(ri, var)
        for line in init_lines or []:
            ri.cw.p(line)
        for line in get_lines:
            ri.cw.p(line)
        if arg.presence_type() == 'present':
            ri.cw.p(f"{var}->_present.{arg.c_name} = 1;")
        ri.cw.block_end()
    ri.cw.p('return 0;')
    ri.cw.block_end()
    ri.cw.nl()


def parse_rsp_nested_prototype(ri, struct, suffix=';'):
    func_args = ['struct ynl_parse_arg *yarg',
                 'const struct nlattr *nested']
    for sel in struct.external_selectors():
        func_args.append('const char *_sel_' + sel.name)
    if struct.submsg:
        func_args.insert(1, 'const char *sel')
    for arg in struct.inherited:
        func_args.append('__u32 ' + arg)

    ri.cw.write_func_prot('int', f'{struct.render_name}_parse', func_args,
                          suffix=suffix)


def parse_rsp_nested(ri, struct):
    if struct.submsg:
        return parse_rsp_submsg(ri, struct)

    parse_rsp_nested_prototype(ri, struct, suffix='')

    local_vars = ['const struct nlattr *attr;',
                  f'{struct.ptr_name}dst = yarg->data;']
    init_lines = []

    if struct.member_list():
        _multi_parse(ri, struct, init_lines, local_vars)
    else:
        # Empty nest
        ri.cw.block_start()
        ri.cw.p('return 0;')
        ri.cw.block_end()
        ri.cw.nl()


def parse_rsp_msg(ri, deref=False):
    if 'reply' not in ri.op[ri.op_mode] and ri.op_mode != 'event':
        return

    func_args = ['const struct nlmsghdr *nlh',
                 'struct ynl_parse_arg *yarg']

    local_vars = [f'{type_name(ri, "reply", deref=deref)} *dst;',
                  'const struct nlattr *attr;']
    init_lines = ['dst = yarg->data;']

    ri.cw.write_func_prot('int', f'{op_prefix(ri, "reply", deref=deref)}_parse', func_args)

    if ri.struct["reply"].member_list():
        _multi_parse(ri, ri.struct["reply"], init_lines, local_vars)
    else:
        # Empty reply
        ri.cw.block_start()
        ri.cw.p('return YNL_PARSE_CB_OK;')
        ri.cw.block_end()
        ri.cw.nl()


def print_req(ri):
    ret_ok = '0'
    ret_err = '-1'
    direction = "request"
    local_vars = ['struct ynl_req_state yrs = { .yarg = { .ys = ys, }, };',
                  'struct nlmsghdr *nlh;',
                  'int err;']

    if 'reply' in ri.op[ri.op_mode]:
        ret_ok = 'rsp'
        ret_err = 'NULL'
        local_vars += [f'{type_name(ri, rdir(direction))} *rsp;']

    if ri.struct["request"].fixed_header:
        local_vars += ['size_t hdr_len;',
                       'void *hdr;']

    for _, attr in ri.struct["request"].member_list():
        if attr.presence_type() == 'count':
            local_vars += ['unsigned int i;']
            break

    print_prototype(ri, direction, terminate=False)
    ri.cw.block_start()
    ri.cw.write_func_lvar(local_vars)

    if ri.family.is_classic():
        ri.cw.p(f"nlh = ynl_msg_start_req(ys, {ri.op.enum_name}, req->_nlmsg_flags);")
    else:
        ri.cw.p(f"nlh = ynl_gemsg_start_req(ys, {ri.nl.get_family_id()}, {ri.op.enum_name}, 1);")

    ri.cw.p(f"ys->req_policy = &{ri.struct['request'].render_name}_nest;")
    ri.cw.p(f"ys->req_hdr_len = {ri.fixed_hdr_len};")
    if 'reply' in ri.op[ri.op_mode]:
        ri.cw.p(f"yrs.yarg.rsp_policy = &{ri.struct['reply'].render_name}_nest;")
    ri.cw.nl()

    if ri.struct['request'].fixed_header:
        ri.cw.p("hdr_len = sizeof(req->_hdr);")
        ri.cw.p("hdr = ynl_nlmsg_put_extra_header(nlh, hdr_len);")
        ri.cw.p("memcpy(hdr, &req->_hdr, hdr_len);")
        ri.cw.nl()

    for _, attr in ri.struct["request"].member_list():
        attr.attr_put(ri, "req")
    ri.cw.nl()

    if 'reply' in ri.op[ri.op_mode]:
        ri.cw.p('rsp = calloc(1, sizeof(*rsp));')
        ri.cw.p('yrs.yarg.data = rsp;')
        ri.cw.p(f"yrs.cb = {op_prefix(ri, 'reply')}_parse;")
        if ri.op.value is not None:
            ri.cw.p(f'yrs.rsp_cmd = {ri.op.enum_name};')
        else:
            ri.cw.p(f'yrs.rsp_cmd = {ri.op.rsp_value};')
        ri.cw.nl()
    ri.cw.p("err = ynl_exec(ys, nlh, &yrs);")
    ri.cw.p('if (err < 0)')
    if 'reply' in ri.op[ri.op_mode]:
        ri.cw.p('goto err_free;')
    else:
        ri.cw.p('return -1;')
    ri.cw.nl()

    ri.cw.p(f"return {ret_ok};")
    ri.cw.nl()

    if 'reply' in ri.op[ri.op_mode]:
        ri.cw.p('err_free:')
        ri.cw.p(f"{call_free(ri, rdir(direction), 'rsp')}")
        ri.cw.p(f"return {ret_err};")

    ri.cw.block_end()


def print_dump(ri):
    direction = "request"
    print_prototype(ri, direction, terminate=False)
    ri.cw.block_start()
    local_vars = ['struct ynl_dump_state yds = {};',
                  'struct nlmsghdr *nlh;',
                  'int err;']

    if ri.struct['request'].fixed_header:
        local_vars += ['size_t hdr_len;',
                       'void *hdr;']

    ri.cw.write_func_lvar(local_vars)

    ri.cw.p('yds.yarg.ys = ys;')
    ri.cw.p(f"yds.yarg.rsp_policy = &{ri.struct['reply'].render_name}_nest;")
    ri.cw.p("yds.yarg.data = NULL;")
    ri.cw.p(f"yds.alloc_sz = sizeof({type_name(ri, rdir(direction))});")
    ri.cw.p(f"yds.cb = {op_prefix(ri, 'reply', deref=True)}_parse;")
    if ri.op.value is not None:
        ri.cw.p(f'yds.rsp_cmd = {ri.op.enum_name};')
    else:
        ri.cw.p(f'yds.rsp_cmd = {ri.op.rsp_value};')
    ri.cw.nl()
    if ri.family.is_classic():
        ri.cw.p(f"nlh = ynl_msg_start_dump(ys, {ri.op.enum_name});")
    else:
        ri.cw.p(f"nlh = ynl_gemsg_start_dump(ys, {ri.nl.get_family_id()}, {ri.op.enum_name}, 1);")

    if ri.struct['request'].fixed_header:
        ri.cw.p("hdr_len = sizeof(req->_hdr);")
        ri.cw.p("hdr = ynl_nlmsg_put_extra_header(nlh, hdr_len);")
        ri.cw.p("memcpy(hdr, &req->_hdr, hdr_len);")
        ri.cw.nl()

    if "request" in ri.op[ri.op_mode]:
        ri.cw.p(f"ys->req_policy = &{ri.struct['request'].render_name}_nest;")
        ri.cw.p(f"ys->req_hdr_len = {ri.fixed_hdr_len};")
        ri.cw.nl()
        for _, attr in ri.struct["request"].member_list():
            attr.attr_put(ri, "req")
    ri.cw.nl()

    ri.cw.p('err = ynl_exec_dump(ys, nlh, &yds);')
    ri.cw.p('if (err < 0)')
    ri.cw.p('goto free_list;')
    ri.cw.nl()

    ri.cw.p('return yds.first;')
    ri.cw.nl()
    ri.cw.p('free_list:')
    ri.cw.p(call_free(ri, rdir(direction), 'yds.first'))
    ri.cw.p('return NULL;')
    ri.cw.block_end()


def call_free(ri, direction, var):
    return f"{op_prefix(ri, direction)}_free({var});"


def free_arg_name(direction):
    if direction:
        return direction_to_suffix[direction][1:]
    return 'obj'


def print_alloc_wrapper(ri, direction, struct=None):
    name = op_prefix(ri, direction)
    struct_name = name
    if ri.type_name_conflict:
        struct_name += '_'

    args = ["void"]
    cnt = "1"
    if struct and struct.in_multi_val:
        args = ["unsigned int n"]
        cnt = "n"

    ri.cw.write_func_prot(f'static inline struct {struct_name} *',
                          f"{name}_alloc", args)
    ri.cw.block_start()
    ri.cw.p(f'return calloc({cnt}, sizeof(struct {struct_name}));')
    ri.cw.block_end()


def print_free_prototype(ri, direction, suffix=';'):
    name = op_prefix(ri, direction)
    struct_name = name
    if ri.type_name_conflict:
        struct_name += '_'
    arg = free_arg_name(direction)
    ri.cw.write_func_prot('void', f"{name}_free", [f"struct {struct_name} *{arg}"], suffix=suffix)


def print_nlflags_set(ri, direction):
    name = op_prefix(ri, direction)
    ri.cw.write_func_prot(f'static inline void', f"{name}_set_nlflags",
                          [f"struct {name} *req", "__u16 nl_flags"])
    ri.cw.block_start()
    ri.cw.p('req->_nlmsg_flags = nl_flags;')
    ri.cw.block_end()
    ri.cw.nl()


def _print_type(ri, direction, struct):
    suffix = f'_{ri.type_name}{direction_to_suffix[direction]}'
    if not direction and ri.type_name_conflict:
        suffix += '_'

    if ri.op_mode == 'dump' and not ri.type_oneside:
        suffix += '_dump'

    ri.cw.block_start(line=f"struct {ri.family.c_name}{suffix}")

    if ri.needs_nlflags(direction):
        ri.cw.p('__u16 _nlmsg_flags;')
        ri.cw.nl()
    if struct.fixed_header:
        ri.cw.p(struct.fixed_header + ' _hdr;')
        ri.cw.nl()

    for type_filter in ['present', 'len', 'count']:
        meta_started = False
        for _, attr in struct.member_list():
            line = attr.presence_member(ri.ku_space, type_filter)
            if line:
                if not meta_started:
                    ri.cw.block_start(line=f"struct")
                    meta_started = True
                ri.cw.p(line)
        if meta_started:
            ri.cw.block_end(line=f'_{type_filter};')
    ri.cw.nl()

    for arg in struct.inherited:
        ri.cw.p(f"__u32 {arg};")

    for _, attr in struct.member_list():
        attr.struct_member(ri)

    ri.cw.block_end(line=';')
    ri.cw.nl()


def print_type(ri, direction):
    _print_type(ri, direction, ri.struct[direction])


def print_type_full(ri, struct):
    _print_type(ri, "", struct)

    if struct.request and struct.in_multi_val:
        print_alloc_wrapper(ri, "", struct)
        ri.cw.nl()
        free_rsp_nested_prototype(ri)
        ri.cw.nl()

        # Name conflicts are too hard to deal with with the current code base,
        # they are very rare so don't bother printing setters in that case.
        if ri.ku_space == 'user' and not ri.type_name_conflict:
            for _, attr in struct.member_list():
                attr.setter(ri, ri.attr_set, "", var="obj")
        ri.cw.nl()


def print_type_helpers(ri, direction, deref=False):
    print_free_prototype(ri, direction)
    ri.cw.nl()

    if ri.needs_nlflags(direction):
        print_nlflags_set(ri, direction)

    if ri.ku_space == 'user' and direction == 'request':
        for _, attr in ri.struct[direction].member_list():
            attr.setter(ri, ri.attr_set, direction, deref=deref)
    ri.cw.nl()


def print_req_type_helpers(ri):
    if ri.type_empty("request"):
        return
    print_alloc_wrapper(ri, "request")
    print_type_helpers(ri, "request")


def print_rsp_type_helpers(ri):
    if 'reply' not in ri.op[ri.op_mode]:
        return
    print_type_helpers(ri, "reply")


def print_parse_prototype(ri, direction, terminate=True):
    suffix = "_rsp" if direction == "reply" else "_req"
    term = ';' if terminate else ''

    ri.cw.write_func_prot('void', f"{ri.op.render_name}{suffix}_parse",
                          ['const struct nlattr **tb',
                           f"struct {ri.op.render_name}{suffix} *req"],
                          suffix=term)


def print_req_type(ri):
    if ri.type_empty("request"):
        return
    print_type(ri, "request")


def print_req_free(ri):
    if 'request' not in ri.op[ri.op_mode]:
        return
    _free_type(ri, 'request', ri.struct['request'])


def print_rsp_type(ri):
    if (ri.op_mode == 'do' or ri.op_mode == 'dump') and 'reply' in ri.op[ri.op_mode]:
        direction = 'reply'
    elif ri.op_mode == 'event':
        direction = 'reply'
    else:
        return
    print_type(ri, direction)


def print_wrapped_type(ri):
    ri.cw.block_start(line=f"{type_name(ri, 'reply')}")
    if ri.op_mode == 'dump':
        ri.cw.p(f"{type_name(ri, 'reply')} *next;")
    elif ri.op_mode == 'notify' or ri.op_mode == 'event':
        ri.cw.p('__u16 family;')
        ri.cw.p('__u8 cmd;')
        ri.cw.p('struct ynl_ntf_base_type *next;')
        ri.cw.p(f"void (*free)({type_name(ri, 'reply')} *ntf);")
    ri.cw.p(f"{type_name(ri, 'reply', deref=True)} obj __attribute__((aligned(8)));")
    ri.cw.block_end(line=';')
    ri.cw.nl()
    print_free_prototype(ri, 'reply')
    ri.cw.nl()


def _free_type_members_iter(ri, struct):
    if struct.free_needs_iter():
        ri.cw.p('unsigned int i;')
        ri.cw.nl()


def _free_type_members(ri, var, struct, ref=''):
    for _, attr in struct.member_list():
        attr.free(ri, var, ref)


def _free_type(ri, direction, struct):
    var = free_arg_name(direction)

    print_free_prototype(ri, direction, suffix='')
    ri.cw.block_start()
    _free_type_members_iter(ri, struct)
    _free_type_members(ri, var, struct)
    if direction:
        ri.cw.p(f'free({var});')
    ri.cw.block_end()
    ri.cw.nl()


def free_rsp_nested_prototype(ri):
        print_free_prototype(ri, "")


def free_rsp_nested(ri, struct):
    _free_type(ri, "", struct)


def print_rsp_free(ri):
    if 'reply' not in ri.op[ri.op_mode]:
        return
    _free_type(ri, 'reply', ri.struct['reply'])


def print_dump_type_free(ri):
    sub_type = type_name(ri, 'reply')

    print_free_prototype(ri, 'reply', suffix='')
    ri.cw.block_start()
    ri.cw.p(f"{sub_type} *next = rsp;")
    ri.cw.nl()
    ri.cw.block_start(line='while ((void *)next != YNL_LIST_END)')
    _free_type_members_iter(ri, ri.struct['reply'])
    ri.cw.p('rsp = next;')
    ri.cw.p('next = rsp->next;')
    ri.cw.nl()

    _free_type_members(ri, 'rsp', ri.struct['reply'], ref='obj.')
    ri.cw.p(f'free(rsp);')
    ri.cw.block_end()
    ri.cw.block_end()
    ri.cw.nl()


def print_ntf_type_free(ri):
    print_free_prototype(ri, 'reply', suffix='')
    ri.cw.block_start()
    _free_type_members_iter(ri, ri.struct['reply'])
    _free_type_members(ri, 'rsp', ri.struct['reply'], ref='obj.')
    ri.cw.p(f'free(rsp);')
    ri.cw.block_end()
    ri.cw.nl()


def print_req_policy_fwd(cw, struct, ri=None, terminate=True):
    if terminate and ri and policy_should_be_static(struct.family):
        return

    if terminate:
        prefix = 'extern '
    else:
        if ri and policy_should_be_static(struct.family):
            prefix = 'static '
        else:
            prefix = ''

    suffix = ';' if terminate else ' = {'

    max_attr = struct.attr_max_val
    if ri:
        name = ri.op.render_name
        if ri.op.dual_policy:
            name += '_' + ri.op_mode
    else:
        name = struct.render_name
    cw.p(f"{prefix}const struct nla_policy {name}_nl_policy[{max_attr.enum_name} + 1]{suffix}")


def print_req_policy(cw, struct, ri=None):
    if ri and ri.op:
        cw.ifdef_block(ri.op.get('config-cond', None))
    print_req_policy_fwd(cw, struct, ri=ri, terminate=False)
    for _, arg in struct.member_list():
        arg.attr_policy(cw)
    cw.p("};")
    cw.ifdef_block(None)
    cw.nl()


def kernel_can_gen_family_struct(family):
    return family.proto == 'genetlink'


def policy_should_be_static(family):
    return family.kernel_policy == 'split' or kernel_can_gen_family_struct(family)


def print_kernel_policy_ranges(family, cw):
    first = True
    for _, attr_set in family.attr_sets.items():
        if attr_set.subset_of:
            continue

        for _, attr in attr_set.items():
            if not attr.request:
                continue
            if 'full-range' not in attr.checks:
                continue

            if first:
                cw.p('/* Integer value ranges */')
                first = False

            sign = '' if attr.type[0] == 'u' else '_signed'
            suffix = 'ULL' if attr.type[0] == 'u' else 'LL'
            cw.block_start(line=f'static const struct netlink_range_validation{sign} {c_lower(attr.enum_name)}_range =')
            members = []
            if 'min' in attr.checks:
                members.append(('min', attr.get_limit_str('min', suffix=suffix)))
            if 'max' in attr.checks:
                members.append(('max', attr.get_limit_str('max', suffix=suffix)))
            cw.write_struct_init(members)
            cw.block_end(line=';')
            cw.nl()


def print_kernel_policy_sparse_enum_validates(family, cw):
    first = True
    for _, attr_set in family.attr_sets.items():
        if attr_set.subset_of:
            continue

        for _, attr in attr_set.items():
            if not attr.request:
                continue
            if not attr.enum_name:
                continue
            if 'sparse' not in attr.checks:
                continue

            if first:
                cw.p('/* Sparse enums validation callbacks */')
                first = False

            sign = '' if attr.type[0] == 'u' else '_signed'
            suffix = 'ULL' if attr.type[0] == 'u' else 'LL'
            cw.write_func_prot('static int', f'{c_lower(attr.enum_name)}_validate',
                               ['const struct nlattr *attr', 'struct netlink_ext_ack *extack'])
            cw.block_start()
            cw.block_start(line=f'switch (nla_get_{attr["type"]}(attr))')
            enum = family.consts[attr['enum']]
            first_entry = True
            for entry in enum.entries.values():
                if first_entry:
                    first_entry = False
                else:
                    cw.p('fallthrough;')
                cw.p(f'case {entry.c_name}:')
            cw.p('return 0;')
            cw.block_end()
            cw.p('NL_SET_ERR_MSG_ATTR(extack, attr, "invalid enum value");')
            cw.p('return -EINVAL;')
            cw.block_end()
            cw.nl()


def print_kernel_op_table_fwd(family, cw, terminate):
    exported = not kernel_can_gen_family_struct(family)

    if not terminate or exported:
        cw.p(f"/* Ops table for {family.ident_name} */")

        pol_to_struct = {'global': 'genl_small_ops',
                         'per-op': 'genl_ops',
                         'split': 'genl_split_ops'}
        struct_type = pol_to_struct[family.kernel_policy]

        if not exported:
            cnt = ""
        elif family.kernel_policy == 'split':
            cnt = 0
            for op in family.ops.values():
                if 'do' in op:
                    cnt += 1
                if 'dump' in op:
                    cnt += 1
        else:
            cnt = len(family.ops)

        qual = 'static const' if not exported else 'const'
        line = f"{qual} struct {struct_type} {family.c_name}_nl_ops[{cnt}]"
        if terminate:
            cw.p(f"extern {line};")
        else:
            cw.block_start(line=line + ' =')

    if not terminate:
        return

    cw.nl()
    for name in family.hooks['pre']['do']['list']:
        cw.write_func_prot('int', c_lower(name),
                           ['const struct genl_split_ops *ops',
                            'struct sk_buff *skb', 'struct genl_info *info'], suffix=';')
    for name in family.hooks['post']['do']['list']:
        cw.write_func_prot('void', c_lower(name),
                           ['const struct genl_split_ops *ops',
                            'struct sk_buff *skb', 'struct genl_info *info'], suffix=';')
    for name in family.hooks['pre']['dump']['list']:
        cw.write_func_prot('int', c_lower(name),
                           ['struct netlink_callback *cb'], suffix=';')
    for name in family.hooks['post']['dump']['list']:
        cw.write_func_prot('int', c_lower(name),
                           ['struct netlink_callback *cb'], suffix=';')

    cw.nl()

    for op_name, op in family.ops.items():
        if op.is_async:
            continue

        if 'do' in op:
            name = c_lower(f"{family.ident_name}-nl-{op_name}-doit")
            cw.write_func_prot('int', name,
                               ['struct sk_buff *skb', 'struct genl_info *info'], suffix=';')

        if 'dump' in op:
            name = c_lower(f"{family.ident_name}-nl-{op_name}-dumpit")
            cw.write_func_prot('int', name,
                               ['struct sk_buff *skb', 'struct netlink_callback *cb'], suffix=';')
    cw.nl()


def print_kernel_op_table_hdr(family, cw):
    print_kernel_op_table_fwd(family, cw, terminate=True)


def print_kernel_op_table(family, cw):
    print_kernel_op_table_fwd(family, cw, terminate=False)
    if family.kernel_policy == 'global' or family.kernel_policy == 'per-op':
        for op_name, op in family.ops.items():
            if op.is_async:
                continue

            cw.ifdef_block(op.get('config-cond', None))
            cw.block_start()
            members = [('cmd', op.enum_name)]
            if 'dont-validate' in op:
                members.append(('validate',
                                ' | '.join([c_upper('genl-dont-validate-' + x)
                                            for x in op['dont-validate']])), )
            for op_mode in ['do', 'dump']:
                if op_mode in op:
                    name = c_lower(f"{family.ident_name}-nl-{op_name}-{op_mode}it")
                    members.append((op_mode + 'it', name))
            if family.kernel_policy == 'per-op':
                struct = Struct(family, op['attribute-set'],
                                type_list=op['do']['request']['attributes'])

                name = c_lower(f"{family.ident_name}-{op_name}-nl-policy")
                members.append(('policy', name))
                members.append(('maxattr', struct.attr_max_val.enum_name))
            if 'flags' in op:
                members.append(('flags', ' | '.join([c_upper('genl-' + x) for x in op['flags']])))
            cw.write_struct_init(members)
            cw.block_end(line=',')
    elif family.kernel_policy == 'split':
        cb_names = {'do':   {'pre': 'pre_doit', 'post': 'post_doit'},
                    'dump': {'pre': 'start', 'post': 'done'}}

        for op_name, op in family.ops.items():
            for op_mode in ['do', 'dump']:
                if op.is_async or op_mode not in op:
                    continue

                cw.ifdef_block(op.get('config-cond', None))
                cw.block_start()
                members = [('cmd', op.enum_name)]
                if 'dont-validate' in op:
                    dont_validate = []
                    for x in op['dont-validate']:
                        if op_mode == 'do' and x in ['dump', 'dump-strict']:
                            continue
                        if op_mode == "dump" and x == 'strict':
                            continue
                        dont_validate.append(x)

                    if dont_validate:
                        members.append(('validate',
                                        ' | '.join([c_upper('genl-dont-validate-' + x)
                                                    for x in dont_validate])), )
                name = c_lower(f"{family.ident_name}-nl-{op_name}-{op_mode}it")
                if 'pre' in op[op_mode]:
                    members.append((cb_names[op_mode]['pre'], c_lower(op[op_mode]['pre'])))
                members.append((op_mode + 'it', name))
                if 'post' in op[op_mode]:
                    members.append((cb_names[op_mode]['post'], c_lower(op[op_mode]['post'])))
                if 'request' in op[op_mode]:
                    struct = Struct(family, op['attribute-set'],
                                    type_list=op[op_mode]['request']['attributes'])

                    if op.dual_policy:
                        name = c_lower(f"{family.ident_name}-{op_name}-{op_mode}-nl-policy")
                    else:
                        name = c_lower(f"{family.ident_name}-{op_name}-nl-policy")
                    members.append(('policy', name))
                    members.append(('maxattr', struct.attr_max_val.enum_name))
                flags = (op['flags'] if 'flags' in op else []) + ['cmd-cap-' + op_mode]
                members.append(('flags', ' | '.join([c_upper('genl-' + x) for x in flags])))
                cw.write_struct_init(members)
                cw.block_end(line=',')
    cw.ifdef_block(None)

    cw.block_end(line=';')
    cw.nl()


def print_kernel_mcgrp_hdr(family, cw):
    if not family.mcgrps['list']:
        return

    cw.block_start('enum')
    for grp in family.mcgrps['list']:
        grp_id = c_upper(f"{family.ident_name}-nlgrp-{grp['name']},")
        cw.p(grp_id)
    cw.block_end(';')
    cw.nl()


def print_kernel_mcgrp_src(family, cw):
    if not family.mcgrps['list']:
        return

    cw.block_start('static const struct genl_multicast_group ' + family.c_name + '_nl_mcgrps[] =')
    for grp in family.mcgrps['list']:
        name = grp['name']
        grp_id = c_upper(f"{family.ident_name}-nlgrp-{name}")
        cw.p('[' + grp_id + '] = { "' + name + '", },')
    cw.block_end(';')
    cw.nl()


def print_kernel_family_struct_hdr(family, cw):
    if not kernel_can_gen_family_struct(family):
        return

    cw.p(f"extern struct genl_family {family.c_name}_nl_family;")
    cw.nl()
    if 'sock-priv' in family.kernel_family:
        cw.p(f'void {family.c_name}_nl_sock_priv_init({family.kernel_family["sock-priv"]} *priv);')
        cw.p(f'void {family.c_name}_nl_sock_priv_destroy({family.kernel_family["sock-priv"]} *priv);')
        cw.nl()


def print_kernel_family_struct_src(family, cw):
    if not kernel_can_gen_family_struct(family):
        return

    if 'sock-priv' in family.kernel_family:
        # Generate "trampolines" to make CFI happy
        cw.write_func("static void", f"__{family.c_name}_nl_sock_priv_init",
                      [f"{family.c_name}_nl_sock_priv_init(priv);"],
                      ["void *priv"])
        cw.nl()
        cw.write_func("static void", f"__{family.c_name}_nl_sock_priv_destroy",
                      [f"{family.c_name}_nl_sock_priv_destroy(priv);"],
                      ["void *priv"])
        cw.nl()

    cw.block_start(f"struct genl_family {family.ident_name}_nl_family __ro_after_init =")
    cw.p('.name\t\t= ' + family.fam_key + ',')
    cw.p('.version\t= ' + family.ver_key + ',')
    cw.p('.netnsok\t= true,')
    cw.p('.parallel_ops\t= true,')
    cw.p('.module\t\t= THIS_MODULE,')
    if family.kernel_policy == 'per-op':
        cw.p(f'.ops\t\t= {family.c_name}_nl_ops,')
        cw.p(f'.n_ops\t\t= ARRAY_SIZE({family.c_name}_nl_ops),')
    elif family.kernel_policy == 'split':
        cw.p(f'.split_ops\t= {family.c_name}_nl_ops,')
        cw.p(f'.n_split_ops\t= ARRAY_SIZE({family.c_name}_nl_ops),')
    if family.mcgrps['list']:
        cw.p(f'.mcgrps\t\t= {family.c_name}_nl_mcgrps,')
        cw.p(f'.n_mcgrps\t= ARRAY_SIZE({family.c_name}_nl_mcgrps),')
    if 'sock-priv' in family.kernel_family:
        cw.p(f'.sock_priv_size\t= sizeof({family.kernel_family["sock-priv"]}),')
        cw.p(f'.sock_priv_init\t= __{family.c_name}_nl_sock_priv_init,')
        cw.p(f'.sock_priv_destroy = __{family.c_name}_nl_sock_priv_destroy,')
    cw.block_end(';')


def uapi_enum_start(family, cw, obj, ckey='', enum_name='enum-name'):
    start_line = 'enum'
    if enum_name in obj:
        if obj[enum_name]:
            start_line = 'enum ' + c_lower(obj[enum_name])
    elif ckey and ckey in obj:
        start_line = 'enum ' + family.c_name + '_' + c_lower(obj[ckey])
    cw.block_start(line=start_line)


def render_uapi_unified(family, cw, max_by_define, separate_ntf):
    max_name = c_upper(family.get('cmd-max-name', f"{family.op_prefix}MAX"))
    cnt_name = c_upper(family.get('cmd-cnt-name', f"__{family.op_prefix}MAX"))
    max_value = f"({cnt_name} - 1)"

    uapi_enum_start(family, cw, family['operations'], 'enum-name')
    val = 0
    for op in family.msgs.values():
        if separate_ntf and ('notify' in op or 'event' in op):
            continue

        suffix = ','
        if op.value != val:
            suffix = f" = {op.value},"
            val = op.value
        cw.p(op.enum_name + suffix)
        val += 1
    cw.nl()
    cw.p(cnt_name + ('' if max_by_define else ','))
    if not max_by_define:
        cw.p(f"{max_name} = {max_value}")
    cw.block_end(line=';')
    if max_by_define:
        cw.p(f"#define {max_name} {max_value}")
    cw.nl()


def render_uapi_directional(family, cw, max_by_define):
    max_name = f"{family.op_prefix}USER_MAX"
    cnt_name = f"__{family.op_prefix}USER_CNT"
    max_value = f"({cnt_name} - 1)"

    cw.block_start(line='enum')
    cw.p(c_upper(f'{family.name}_MSG_USER_NONE = 0,'))
    val = 0
    for op in family.msgs.values():
        if 'do' in op and 'event' not in op:
            suffix = ','
            if op.value and op.value != val:
                suffix = f" = {op.value},"
                val = op.value
            cw.p(op.enum_name + suffix)
            val += 1
    cw.nl()
    cw.p(cnt_name + ('' if max_by_define else ','))
    if not max_by_define:
        cw.p(f"{max_name} = {max_value}")
    cw.block_end(line=';')
    if max_by_define:
        cw.p(f"#define {max_name} {max_value}")
    cw.nl()

    max_name = f"{family.op_prefix}KERNEL_MAX"
    cnt_name = f"__{family.op_prefix}KERNEL_CNT"
    max_value = f"({cnt_name} - 1)"

    cw.block_start(line='enum')
    cw.p(c_upper(f'{family.name}_MSG_KERNEL_NONE = 0,'))
    val = 0
    for op in family.msgs.values():
        if ('do' in op and 'reply' in op['do']) or 'notify' in op or 'event' in op:
            enum_name = op.enum_name
            if 'event' not in op and 'notify' not in op:
                enum_name = f'{enum_name}_REPLY'

            suffix = ','
            if op.value and op.value != val:
                suffix = f" = {op.value},"
                val = op.value
            cw.p(enum_name + suffix)
            val += 1
    cw.nl()
    cw.p(cnt_name + ('' if max_by_define else ','))
    if not max_by_define:
        cw.p(f"{max_name} = {max_value}")
    cw.block_end(line=';')
    if max_by_define:
        cw.p(f"#define {max_name} {max_value}")
    cw.nl()


def render_uapi(family, cw):
    hdr_prot = f"_UAPI_LINUX_{c_upper(family.uapi_header_name)}_H"
    hdr_prot = hdr_prot.replace('/', '_')
    cw.p('#ifndef ' + hdr_prot)
    cw.p('#define ' + hdr_prot)
    cw.nl()

    defines = [(family.fam_key, family["name"]),
               (family.ver_key, family.get('version', 1))]
    cw.writes_defines(defines)
    cw.nl()

    defines = []
    for const in family['definitions']:
        if const.get('header'):
            continue

        if const['type'] != 'const':
            cw.writes_defines(defines)
            defines = []
            cw.nl()

        # Write kdoc for enum and flags (one day maybe also structs)
        if const['type'] == 'enum' or const['type'] == 'flags':
            enum = family.consts[const['name']]

            if enum.header:
                continue

            if enum.has_doc():
                if enum.has_entry_doc():
                    cw.p('/**')
                    doc = ''
                    if 'doc' in enum:
                        doc = ' - ' + enum['doc']
                    cw.write_doc_line(enum.enum_name + doc)
                else:
                    cw.p('/*')
                    cw.write_doc_line(enum['doc'], indent=False)
                for entry in enum.entries.values():
                    if entry.has_doc():
                        doc = '@' + entry.c_name + ': ' + entry['doc']
                        cw.write_doc_line(doc)
                cw.p(' */')

            uapi_enum_start(family, cw, const, 'name')
            name_pfx = const.get('name-prefix', f"{family.ident_name}-{const['name']}-")
            for entry in enum.entries.values():
                suffix = ','
                if entry.value_change:
                    suffix = f" = {entry.user_value()}" + suffix
                cw.p(entry.c_name + suffix)

            if const.get('render-max', False):
                cw.nl()
                cw.p('/* private: */')
                if const['type'] == 'flags':
                    max_name = c_upper(name_pfx + 'mask')
                    max_val = f' = {enum.get_mask()},'
                    cw.p(max_name + max_val)
                else:
                    cnt_name = enum.enum_cnt_name
                    max_name = c_upper(name_pfx + 'max')
                    if not cnt_name:
                        cnt_name = '__' + name_pfx + 'max'
                    cw.p(c_upper(cnt_name) + ',')
                    cw.p(max_name + ' = (' + c_upper(cnt_name) + ' - 1)')
            cw.block_end(line=';')
            cw.nl()
        elif const['type'] == 'const':
            defines.append([c_upper(family.get('c-define-name',
                                               f"{family.ident_name}-{const['name']}")),
                            const['value']])

    if defines:
        cw.writes_defines(defines)
        cw.nl()

    max_by_define = family.get('max-by-define', False)

    for _, attr_set in family.attr_sets.items():
        if attr_set.subset_of:
            continue

        max_value = f"({attr_set.cnt_name} - 1)"

        val = 0
        uapi_enum_start(family, cw, attr_set.yaml, 'enum-name')
        for _, attr in attr_set.items():
            suffix = ','
            if attr.value != val:
                suffix = f" = {attr.value},"
                val = attr.value
            val += 1
            cw.p(attr.enum_name + suffix)
        if attr_set.items():
            cw.nl()
        cw.p(attr_set.cnt_name + ('' if max_by_define else ','))
        if not max_by_define:
            cw.p(f"{attr_set.max_name} = {max_value}")
        cw.block_end(line=';')
        if max_by_define:
            cw.p(f"#define {attr_set.max_name} {max_value}")
        cw.nl()

    # Commands
    separate_ntf = 'async-prefix' in family['operations']

    if family.msg_id_model == 'unified':
        render_uapi_unified(family, cw, max_by_define, separate_ntf)
    elif family.msg_id_model == 'directional':
        render_uapi_directional(family, cw, max_by_define)
    else:
        raise Exception(f'Unsupported message enum-model {family.msg_id_model}')

    if separate_ntf:
        uapi_enum_start(family, cw, family['operations'], enum_name='async-enum')
        for op in family.msgs.values():
            if separate_ntf and not ('notify' in op or 'event' in op):
                continue

            suffix = ','
            if 'value' in op:
                suffix = f" = {op['value']},"
            cw.p(op.enum_name + suffix)
        cw.block_end(line=';')
        cw.nl()

    # Multicast
    defines = []
    for grp in family.mcgrps['list']:
        name = grp['name']
        defines.append([c_upper(grp.get('c-define-name', f"{family.ident_name}-mcgrp-{name}")),
                        f'{name}'])
    cw.nl()
    if defines:
        cw.writes_defines(defines)
        cw.nl()

    cw.p(f'#endif /* {hdr_prot} */')


def _render_user_ntf_entry(ri, op):
    if not ri.family.is_classic():
        ri.cw.block_start(line=f"[{op.enum_name}] = ")
    else:
        crud_op = ri.family.req_by_value[op.rsp_value]
        ri.cw.block_start(line=f"[{crud_op.enum_name}] = ")
    ri.cw.p(f".alloc_sz\t= sizeof({type_name(ri, 'event')}),")
    ri.cw.p(f".cb\t\t= {op_prefix(ri, 'reply', deref=True)}_parse,")
    ri.cw.p(f".policy\t\t= &{ri.struct['reply'].render_name}_nest,")
    ri.cw.p(f".free\t\t= (void *){op_prefix(ri, 'notify')}_free,")
    ri.cw.block_end(line=',')


def render_user_family(family, cw, prototype):
    symbol = f'const struct ynl_family ynl_{family.c_name}_family'
    if prototype:
        cw.p(f'extern {symbol};')
        return

    if family.ntfs:
        cw.block_start(line=f"static const struct ynl_ntf_info {family.c_name}_ntf_info[] = ")
        for ntf_op_name, ntf_op in family.ntfs.items():
            if 'notify' in ntf_op:
                op = family.ops[ntf_op['notify']]
                ri = RenderInfo(cw, family, "user", op, "notify")
            elif 'event' in ntf_op:
                ri = RenderInfo(cw, family, "user", ntf_op, "event")
            else:
                raise Exception('Invalid notification ' + ntf_op_name)
            _render_user_ntf_entry(ri, ntf_op)
        for op_name, op in family.ops.items():
            if 'event' not in op:
                continue
            ri = RenderInfo(cw, family, "user", op, "event")
            _render_user_ntf_entry(ri, op)
        cw.block_end(line=";")
        cw.nl()

    cw.block_start(f'{symbol} = ')
    cw.p(f'.name\t\t= "{family.c_name}",')
    if family.is_classic():
        cw.p(f'.is_classic\t= true,')
        cw.p(f'.classic_id\t= {family.get("protonum")},')
    if family.is_classic():
        if family.fixed_header:
            cw.p(f'.hdr_len\t= sizeof(struct {c_lower(family.fixed_header)}),')
    elif family.fixed_header:
        cw.p(f'.hdr_len\t= sizeof(struct genlmsghdr) + sizeof(struct {c_lower(family.fixed_header)}),')
    else:
        cw.p('.hdr_len\t= sizeof(struct genlmsghdr),')
    if family.ntfs:
        cw.p(f".ntf_info\t= {family.c_name}_ntf_info,")
        cw.p(f".ntf_info_size\t= YNL_ARRAY_SIZE({family.c_name}_ntf_info),")
    cw.block_end(line=';')


def family_contains_bitfield32(family):
    for _, attr_set in family.attr_sets.items():
        if attr_set.subset_of:
            continue
        for _, attr in attr_set.items():
            if attr.type == "bitfield32":
                return True
    return False


def find_kernel_root(full_path):
    sub_path = ''
    while True:
        sub_path = os.path.join(os.path.basename(full_path), sub_path)
        full_path = os.path.dirname(full_path)
        maintainers = os.path.join(full_path, "MAINTAINERS")
        if os.path.exists(maintainers):
            return full_path, sub_path[:-1]


def main():
    parser = argparse.ArgumentParser(description='Netlink simple parsing generator')
    parser.add_argument('--mode', dest='mode', type=str, required=True,
                        choices=('user', 'kernel', 'uapi'))
    parser.add_argument('--spec', dest='spec', type=str, required=True)
    parser.add_argument('--header', dest='header', action='store_true', default=None)
    parser.add_argument('--source', dest='header', action='store_false')
    parser.add_argument('--user-header', nargs='+', default=[])
    parser.add_argument('--cmp-out', action='store_true', default=None,
                        help='Do not overwrite the output file if the new output is identical to the old')
    parser.add_argument('--exclude-op', action='append', default=[])
    parser.add_argument('-o', dest='out_file', type=str, default=None)
    args = parser.parse_args()

    if args.header is None:
        parser.error("--header or --source is required")

    exclude_ops = [re.compile(expr) for expr in args.exclude_op]

    try:
        parsed = Family(args.spec, exclude_ops)
        if parsed.license != '((GPL-2.0 WITH Linux-syscall-note) OR BSD-3-Clause)':
            print('Spec license:', parsed.license)
            print('License must be: ((GPL-2.0 WITH Linux-syscall-note) OR BSD-3-Clause)')
            os.sys.exit(1)
    except yaml.YAMLError as exc:
        print(exc)
        os.sys.exit(1)
        return

    cw = CodeWriter(BaseNlLib(), args.out_file, overwrite=(not args.cmp_out))

    _, spec_kernel = find_kernel_root(args.spec)
    if args.mode == 'uapi' or args.header:
        cw.p(f'/* SPDX-License-Identifier: {parsed.license} */')
    else:
        cw.p(f'// SPDX-License-Identifier: {parsed.license}')
    cw.p("/* Do not edit directly, auto-generated from: */")
    cw.p(f"/*\t{spec_kernel} */")
    cw.p(f"/* YNL-GEN {args.mode} {'header' if args.header else 'source'} */")
    if args.exclude_op or args.user_header:
        line = ''
        line += ' --user-header '.join([''] + args.user_header)
        line += ' --exclude-op '.join([''] + args.exclude_op)
        cw.p(f'/* YNL-ARG{line} */')
    cw.nl()

    if args.mode == 'uapi':
        render_uapi(parsed, cw)
        return

    hdr_prot = f"_LINUX_{parsed.c_name.upper()}_GEN_H"
    if args.header:
        cw.p('#ifndef ' + hdr_prot)
        cw.p('#define ' + hdr_prot)
        cw.nl()

    if args.out_file:
        hdr_file = os.path.basename(args.out_file[:-2]) + ".h"
    else:
        hdr_file = "generated_header_file.h"

    if args.mode == 'kernel':
        cw.p('#include <net/netlink.h>')
        cw.p('#include <net/genetlink.h>')
        cw.nl()
        if not args.header:
            if args.out_file:
                cw.p(f'#include "{hdr_file}"')
            cw.nl()
        headers = ['uapi/' + parsed.uapi_header]
        headers += parsed.kernel_family.get('headers', [])
    else:
        cw.p('#include <stdlib.h>')
        cw.p('#include <string.h>')
        if args.header:
            cw.p('#include <linux/types.h>')
            if family_contains_bitfield32(parsed):
                cw.p('#include <linux/netlink.h>')
        else:
            cw.p(f'#include "{hdr_file}"')
            cw.p('#include "ynl.h"')
        headers = []
    for definition in parsed['definitions'] + parsed['attribute-sets']:
        if 'header' in definition:
            headers.append(definition['header'])
    if args.mode == 'user':
        headers.append(parsed.uapi_header)
    seen_header = []
    for one in headers:
        if one not in seen_header:
            cw.p(f"#include <{one}>")
            seen_header.append(one)
    cw.nl()

    if args.mode == "user":
        if not args.header:
            cw.p("#include <linux/genetlink.h>")
            cw.nl()
            for one in args.user_header:
                cw.p(f'#include "{one}"')
        else:
            cw.p('struct ynl_sock;')
            cw.nl()
            render_user_family(parsed, cw, True)
        cw.nl()

    if args.mode == "kernel":
        if args.header:
            for _, struct in sorted(parsed.pure_nested_structs.items()):
                if struct.request:
                    cw.p('/* Common nested types */')
                    break
            for attr_set, struct in sorted(parsed.pure_nested_structs.items()):
                if struct.request:
                    print_req_policy_fwd(cw, struct)
            cw.nl()

            if parsed.kernel_policy == 'global':
                cw.p(f"/* Global operation policy for {parsed.name} */")

                struct = Struct(parsed, parsed.global_policy_set, type_list=parsed.global_policy)
                print_req_policy_fwd(cw, struct)
                cw.nl()

            if parsed.kernel_policy in {'per-op', 'split'}:
                for op_name, op in parsed.ops.items():
                    if 'do' in op and 'event' not in op:
                        ri = RenderInfo(cw, parsed, args.mode, op, "do")
                        print_req_policy_fwd(cw, ri.struct['request'], ri=ri)
                        cw.nl()

            print_kernel_op_table_hdr(parsed, cw)
            print_kernel_mcgrp_hdr(parsed, cw)
            print_kernel_family_struct_hdr(parsed, cw)
        else:
            print_kernel_policy_ranges(parsed, cw)
            print_kernel_policy_sparse_enum_validates(parsed, cw)

            for _, struct in sorted(parsed.pure_nested_structs.items()):
                if struct.request:
                    cw.p('/* Common nested types */')
                    break
            for attr_set, struct in sorted(parsed.pure_nested_structs.items()):
                if struct.request:
                    print_req_policy(cw, struct)
            cw.nl()

            if parsed.kernel_policy == 'global':
                cw.p(f"/* Global operation policy for {parsed.name} */")

                struct = Struct(parsed, parsed.global_policy_set, type_list=parsed.global_policy)
                print_req_policy(cw, struct)
                cw.nl()

            for op_name, op in parsed.ops.items():
                if parsed.kernel_policy in {'per-op', 'split'}:
                    for op_mode in ['do', 'dump']:
                        if op_mode in op and 'request' in op[op_mode]:
                            cw.p(f"/* {op.enum_name} - {op_mode} */")
                            ri = RenderInfo(cw, parsed, args.mode, op, op_mode)
                            print_req_policy(cw, ri.struct['request'], ri=ri)
                            cw.nl()

            print_kernel_op_table(parsed, cw)
            print_kernel_mcgrp_src(parsed, cw)
            print_kernel_family_struct_src(parsed, cw)

    if args.mode == "user":
        if args.header:
            cw.p('/* Enums */')
            put_op_name_fwd(parsed, cw)

            for name, const in parsed.consts.items():
                if isinstance(const, EnumSet):
                    put_enum_to_str_fwd(parsed, cw, const)
            cw.nl()

            cw.p('/* Common nested types */')
            for attr_set, struct in parsed.pure_nested_structs.items():
                ri = RenderInfo(cw, parsed, args.mode, "", "", attr_set)
                print_type_full(ri, struct)

            for op_name, op in parsed.ops.items():
                cw.p(f"/* ============== {op.enum_name} ============== */")

                if 'do' in op and 'event' not in op:
                    cw.p(f"/* {op.enum_name} - do */")
                    ri = RenderInfo(cw, parsed, args.mode, op, "do")
                    print_req_type(ri)
                    print_req_type_helpers(ri)
                    cw.nl()
                    print_rsp_type(ri)
                    print_rsp_type_helpers(ri)
                    cw.nl()
                    print_req_prototype(ri)
                    cw.nl()

                if 'dump' in op:
                    cw.p(f"/* {op.enum_name} - dump */")
                    ri = RenderInfo(cw, parsed, args.mode, op, 'dump')
                    print_req_type(ri)
                    print_req_type_helpers(ri)
                    if not ri.type_consistent or ri.type_oneside:
                        print_rsp_type(ri)
                    print_wrapped_type(ri)
                    print_dump_prototype(ri)
                    cw.nl()

                if op.has_ntf:
                    cw.p(f"/* {op.enum_name} - notify */")
                    ri = RenderInfo(cw, parsed, args.mode, op, 'notify')
                    if not ri.type_consistent:
                        raise Exception(f'Only notifications with consistent types supported ({op.name})')
                    print_wrapped_type(ri)

            for op_name, op in parsed.ntfs.items():
                if 'event' in op:
                    ri = RenderInfo(cw, parsed, args.mode, op, 'event')
                    cw.p(f"/* {op.enum_name} - event */")
                    print_rsp_type(ri)
                    cw.nl()
                    print_wrapped_type(ri)
            cw.nl()
        else:
            cw.p('/* Enums */')
            put_op_name(parsed, cw)

            for name, const in parsed.consts.items():
                if isinstance(const, EnumSet):
                    put_enum_to_str(parsed, cw, const)
            cw.nl()

            has_recursive_nests = False
            cw.p('/* Policies */')
            for struct in parsed.pure_nested_structs.values():
                if struct.recursive:
                    put_typol_fwd(cw, struct)
                    has_recursive_nests = True
            if has_recursive_nests:
                cw.nl()
            for struct in parsed.pure_nested_structs.values():
                put_typol(cw, struct)
            for name in parsed.root_sets:
                struct = Struct(parsed, name)
                put_typol(cw, struct)

            cw.p('/* Common nested types */')
            if has_recursive_nests:
                for attr_set, struct in parsed.pure_nested_structs.items():
                    ri = RenderInfo(cw, parsed, args.mode, "", "", attr_set)
                    free_rsp_nested_prototype(ri)
                    if struct.request:
                        put_req_nested_prototype(ri, struct)
                    if struct.reply:
                        parse_rsp_nested_prototype(ri, struct)
                cw.nl()
            for attr_set, struct in parsed.pure_nested_structs.items():
                ri = RenderInfo(cw, parsed, args.mode, "", "", attr_set)

                free_rsp_nested(ri, struct)
                if struct.request:
                    put_req_nested(ri, struct)
                if struct.reply:
                    parse_rsp_nested(ri, struct)

            for op_name, op in parsed.ops.items():
                cw.p(f"/* ============== {op.enum_name} ============== */")
                if 'do' in op and 'event' not in op:
                    cw.p(f"/* {op.enum_name} - do */")
                    ri = RenderInfo(cw, parsed, args.mode, op, "do")
                    print_req_free(ri)
                    print_rsp_free(ri)
                    parse_rsp_msg(ri)
                    print_req(ri)
                    cw.nl()

                if 'dump' in op:
                    cw.p(f"/* {op.enum_name} - dump */")
                    ri = RenderInfo(cw, parsed, args.mode, op, "dump")
                    if not ri.type_consistent or ri.type_oneside:
                        parse_rsp_msg(ri, deref=True)
                    print_req_free(ri)
                    print_dump_type_free(ri)
                    print_dump(ri)
                    cw.nl()

                if op.has_ntf:
                    cw.p(f"/* {op.enum_name} - notify */")
                    ri = RenderInfo(cw, parsed, args.mode, op, 'notify')
                    if not ri.type_consistent:
                        raise Exception(f'Only notifications with consistent types supported ({op.name})')
                    print_ntf_type_free(ri)

            for op_name, op in parsed.ntfs.items():
                if 'event' in op:
                    cw.p(f"/* {op.enum_name} - event */")

                    ri = RenderInfo(cw, parsed, args.mode, op, "do")
                    parse_rsp_msg(ri)

                    ri = RenderInfo(cw, parsed, args.mode, op, "event")
                    print_ntf_type_free(ri)
            cw.nl()
            render_user_family(parsed, cw, False)

    if args.header:
        cw.p(f'#endif /* {hdr_prot} */')


if __name__ == "__main__":
    main()
