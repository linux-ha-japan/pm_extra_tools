#!/usr/libexec/platform-python
# -*- coding: utf-8 -*-

# pm_pcsgen : Pacemaker CIB(xml) and PCS(sh) generator
#
# Copyright (C) 2020-2021 NIPPON TELEGRAPH AND TELEPHONE CORPORATION
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public
# License along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

import os
import sys
import codecs
import re
import shlex
import subprocess
from enum import Enum
from enum import IntEnum

CONF = '/usr/share/pm_extra_tools/pm_pcsgen.conf'
U8 = 'utf-8'

# モード識別子(処理中の表を識別)
class Mode(Enum):
  NODE = 'Node'
  PROP = 'Property'
  RDEF = 'RscDefaults'
  ODEF = 'OpDefaults'
  RSCS = 'Resources'
  ATTR = 'Attributes'
  PRIM = 'Primitive'
  STNT = 'Stonith'
  STLV = 'StonithLV'
  LOCN = 'LocationNode'
  LOCR = 'LocationRule'
  COLO = 'Colocation'
  ORDR = 'Order'
  ALRT = 'Alert'
  CNFG = 'Config'
  SKIP = 'skip'      # 次の表ヘッダまでスキップ
  GRUP = 'Group'
  CLNE = 'Clone'
  PROM = 'Promotable'
  RMET = 'RscMeta'
  RUTI = 'RscUtilzation'
  AREC = 'AlertRecipient'

# {表ヘッダ文字列: モード識別子}
MODE = {
  'node':              Mode.NODE.value,
  'property':          Mode.PROP.value,
  'rsc_defaults':      Mode.RDEF.value,
  'op_defaults':       Mode.ODEF.value,
  'resources':         Mode.RSCS.value,
  'rsc_attributes':    Mode.ATTR.value,
  'primitive':         Mode.PRIM.value,
  'stonith':           Mode.STNT.value,
  'stonith_level':     Mode.STLV.value,
  'location_node':     Mode.LOCN.value,
  'location_rule':     Mode.LOCR.value,
  'colocation':        Mode.COLO.value,
  'order':             Mode.ORDR.value,
  'alert':             Mode.ALRT.value,
  'additional_config': Mode.CNFG.value
}

# Mode.PRIM.valueのサブモード
PRIM_PROP = 'p'      # Prop(erty)
PRIM_ATTR = 'a'      # Attr(ibutes)
PRIM_OPER = 'o'      # Oper(ation)
PRIM_MODE = [PRIM_PROP,PRIM_ATTR,PRIM_OPER]

# Mode.STNT.valueのサブモード
STNT_PROP = 'p'      # Prop(erty)
STNT_ATTR = 'a'      # Attr(ibutes)
STNT_OPER = 'o'      # Oper(ation)
STNT_MODE = [STNT_PROP,STNT_ATTR,STNT_OPER]

# Mode.ALRT.valueのサブモード
ALRT_PATH = 'p'      # Path
ALRT_ATTR = 'a'      # Attr(ibutes)
ALRT_RECI = 'r'      # Reci(pient)
ALRT_MODE = [ALRT_PATH,ALRT_ATTR,ALRT_RECI]

# 必須列名
RQCLM = {
  (Mode.PRIM.value,PRIM_PROP): ['id','class','provider','type'],
  (Mode.PRIM.value,PRIM_ATTR): ['type','name','value'],
  (Mode.PRIM.value,PRIM_OPER): ['type'],
  (Mode.STNT.value,STNT_PROP): ['id','type'],
  (Mode.STNT.value,STNT_ATTR): ['type','name','value'],
  (Mode.STNT.value,STNT_OPER): ['type'],
  (Mode.ALRT.value,ALRT_PATH): ['path'],
  (Mode.ALRT.value,ALRT_ATTR): ['type','name','value'],
  (Mode.ALRT.value,ALRT_RECI): ['recipient'],
  (Mode.NODE.value,None): ['uname','type','name','value'],
  (Mode.PROP.value,None): ['name','value'],
  (Mode.RDEF.value,None): ['name','value'],
  (Mode.ODEF.value,None): ['name','value'],
  (Mode.RSCS.value,None): ['resourceitem','id'],
  (Mode.ATTR.value,None): ['id','name','value'],
  (Mode.STLV.value,None): ['node','id','level'],
  (Mode.LOCN.value,None): ['rsc','prefers/avoids','node','score'],
  (Mode.LOCR.value,None): ['rsc','score','bool_op','attribute','op','value','role'],
  (Mode.COLO.value,None): ['rsc','with-rsc','score','rsc-role','with-rsc-role'],
  (Mode.ORDR.value,None): ['first-rsc','then-rsc','kind','first-action','then-action','symmetrical'],
  (Mode.CNFG.value,None): ['config']
}

# 種別
RSC_TYPE = {
  'primitive':  Mode.PRIM.value,
  'stonith':    Mode.STNT.value,
  'group':      Mode.GRUP.value,
  'clone':      Mode.CLNE.value,
  'promotable': Mode.PROM.value
}
NODE_ATTR_TYPE = ['attribute','utilization']
PRIM_ATTR_TYPE = ['options','meta','utilization']
STNT_ATTR_TYPE = ['options','meta','utilization']
ALRT_ATTR_TYPE = ['options','meta']
ELSE_ATTR_TYPE = ['meta']

LOC_NODE_PREAVO = ['prefers','avoids']
LOC_RULE_UNARY = ['defined','not_defined']
ORDR_ACTION = ['start','promote','demote','stop']

class RC(IntEnum):
  SUCCESS        = 0
  ERROR          = 1
  WARN           = 2
  ERROR_NONFATAL = 3

# エラー|警告が発生した場合、Trueに設定
errflg,skipflg,warnflg = False,False,False

# State,Created,Updated
ATTR_S,ATTR_C,ATTR_U = '_s','_c','_u'

# 表ヘッダ列番号
HDR_POS = 1

# 'pcs -f {pcs_file} [command]'
PCSF = {
  Mode.NODE.value: r'{pcsf} node',
  Mode.PROP.value: r'{pcsf} property set',
  Mode.RDEF.value: r'{pcsf} resource defaults update',
  Mode.ODEF.value: r'{pcsf} resource op defaults update',
  Mode.PRIM.value: r'{pcsf} resource create',
  Mode.STNT.value: r'{pcsf} stonith create',
  Mode.STLV.value: r'{pcsf} stonith level add',
  Mode.GRUP.value: r'{pcsf} resource group add',
  Mode.CLNE.value: r'{pcsf} resource clone',
  Mode.PROM.value: r'{pcsf} resource promotable',
  Mode.RMET.value: r'{pcsf} resource meta',
  Mode.RUTI.value: r'{pcsf} resource utilization',
  Mode.LOCN.value: r'{pcsf} constraint location',
  Mode.LOCR.value: r'{pcsf} constraint location',
  Mode.COLO.value: r'{pcsf} constraint colocation add',
  Mode.ORDR.value: r'{pcsf} constraint order',
  Mode.ALRT.value: r'{pcsf} alert create',
  Mode.AREC.value: r'{pcsf} alert recipient add'
}

# PCSファイルに出力するコメント
CMNT = {
  Mode.NODE.value: '### Cluster Node',
  Mode.PROP.value: '### Cluster Option',
  Mode.RDEF.value: '### Resource Defaults',
  Mode.ODEF.value: '### Operation Defaults',
  Mode.PRIM.value: '### Primitive Configuration',
  Mode.STNT.value: '### STONITH Configuration',
  Mode.STLV.value: '### STONITH Level',
  Mode.GRUP.value: '### Group Configuration',
  Mode.CLNE.value: '### Clone Configuration',
  Mode.PROM.value: '### Promotable Clone Configuration',
  Mode.LOCN.value: '### Resource Location',
  Mode.LOCR.value: '### Resource Location',
  Mode.COLO.value: '### Resource Colocation',
  Mode.ORDR.value: '### Resource Order',
  Mode.ALRT.value: '### Alert Configuration',
  Mode.CNFG.value: '### Additional Config'
}

# 実行時に出力するメッセージ用
TBLN = {
  Mode.NODE.value: 'クラスタ・ノード表',
  Mode.PROP.value: 'クラスタ・プロパティ表',
  Mode.RDEF.value: 'リソース・デフォルト表',
  Mode.ODEF.value: 'オペレーション・デフォルト表',
  Mode.RSCS.value: 'リソース構成表',
  Mode.ATTR.value: 'リソース構成パラメータ表',
  Mode.PRIM.value: 'Primitiveリソース表',
  Mode.STNT.value: 'STONITHリソース表',
  Mode.STLV.value: 'STONITHの実行順序表',
  Mode.LOCN.value: 'リソース配置制約(ノード)表',
  Mode.LOCR.value: 'リソース配置制約(ルール)表',
  Mode.COLO.value: 'リソース同居制約表',
  Mode.ORDR.value: 'リソース起動順序制約表',
  Mode.ALRT.value: 'Alert設定表',
  Mode.CNFG.value: '追加設定表'
}

class Gen:
  mode = (None,None)
  pcr = []          # 親子関係 (parent and child relationship)
  attrd = {}
  rr = None         # XMLドキュメント (<{Mode.RSCS}>...</{Mode.RSCS}>のroot要素を指しておく)
  xr = None         # XMLドキュメント (テンポラリ作業用。root要素を指しておく)
  xc = None         # XMLドキュメントの作業中の要素を指しておく
  lno = 0           # line no
  req_reci = False  # Alert表のrecipient列にデータが必要な状態の間、Trueを設定

  def __init__(self):
    if not self.parse_option():
      exit(RC.ERROR)
    if not self.parse_config():
      exit(RC.ERROR)
    self.pcsf = f'pcs -f {self.outxml}'
    for (k,x) in PCSF.items():
      PCSF[k] = x.replace(r'{pcsf}',self.pcsf)
    try:
      from xml.dom.minidom import getDOMImplementation
      self.doc = getDOMImplementation().createDocument(None,'csv',None)
      self.root = self.doc.documentElement
    except Exception as e:
      log.innererr('DOM文書オブジェクトの生成に失敗しました',e)
      exit(RC.ERROR)

  '''
    オプション解析
    [引数]
      なし
    [戻り値]
      True  : OK
      False : NG(不正なオプションあり)
  '''
  def parse_option(self):
    import argparse
    import pathlib
    i = 'CSV_FILE'
    x = '<CSV_FILE>.xml'
    s = '<CSV_FILE>.sh'
    d = 'CSV_FILE supports UTF-8 and Shift_JIS.'
    p = argparse.ArgumentParser(
      usage=f'%(prog)s [options] {i}',
      description=f"To set 'cluster node (NODE table)', cluster must be live.\n{d}",
      prog='pm_pcsgen',
      formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument('-$','--version',action='version',version='1.2',
      help='Print %(prog)s version information.')
    p.add_argument('-V','--verbose',action='count',dest='loglv',default=Log.WARN,
      help='Increase debug output.')
    p.add_argument('-l','--live',action='store_const',dest='live',const=True,default=False,
      help="Generate CIB from live cluster's CIB.")
    p.add_argument('--xml',dest='cib_file',
      help=f'Write generated CIB to the named xml file.\ndefault: {x}')
    p.add_argument('--sh',dest='pcs_file',
      help=f'Write generated PCS to the named script file.\ndefault: {s}')
    try:
      opts,args = p.parse_known_args()
    except SystemExit as e:
      if str(e) != '0':
        log.error_r('\n')
        return False
      sys.exit(RC.SUCCESS)
    except Exception:
      log.error('オプションの解析に失敗しました')
      return False
    if len(args) != 1:
      if len(args) == 0:
        log.error('入力ファイルが指定されていません')
      else:
        log.error('入力ファイルが複数指定されています')
      return False
    log.lv = opts.loglv
    self.live = opts.live
    self.input = args[0]
    r,e = os.path.splitext(os.path.basename(self.input))
    self.outxml = opts.cib_file if opts.cib_file else f'{r}.xml'
    self.outsh = opts.pcs_file if opts.pcs_file else f'{r}.sh'
    log.set_msginfo(self.outxml,self.outsh)
    log.debug(f'input[{os.path.abspath(self.input)}] '
              f'outxml[{os.path.abspath(self.outxml)}] outsh[{os.path.abspath(self.outsh)}]')
    if not os.path.isfile(self.input):
      log.error(f'入力ファイル [{self.input}] が見つかりません')
      return False
    if pathlib.Path(self.outxml).resolve() == pathlib.Path(self.outsh).resolve():
      log.error('CIBとPCSの出力先が同じです')
      return False
    return True

  '''
    設定ファイル解析
    [引数]
      なし
    [戻り値]
      True  : OK
      False : NG
  '''
  def parse_config(self):
    import configparser
    self.filter = {}
    try:
      if not os.path.isfile(CONF):
        log.warn(f'CONFファイル [{CONF}] が見つかりません')
        return True
      p = configparser.ConfigParser()
      p.read(CONF)
      for s in p.sections():
        self.filter[s] = dict(p.items(s))
      log.debug(f'filter: {self.filter}')
      return True
    except Exception as e:
      log.innererr('CONFファイルの解析に失敗しました',e)
      return False

  def skip_mode(self,chg=True):
    if chg:
      self.mode = (Mode.SKIP.value,self.mode[1])

  '''
    表ヘッダ解析
    [引数]
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG
  '''
  def parse_hdr(self,csvl):
    def fmterr():
      log.fmterr_l(self.msg_inval_fmt(TBLN[self.mode[0]]))
      self.skip_mode()
    def submode(x,ATTR):
      self.mode = (self.mode[0],x)
      log.debug_l(f'サブモードを[{self.mode[1]}]にセットしました')
      if self.mode[1] == ATTR:
        self.attrd = {}
    x = csvl[HDR_POS].lower()
    if self.mode[0] == Mode.PRIM.value and x in PRIM_MODE:
      if (not self.mode[1] and x != PRIM_PROP or self.mode[1] and x == PRIM_PROP):
        fmterr()
        return True
      submode(x,PRIM_ATTR)
      return True
    elif self.mode[0] == Mode.STNT.value and x in STNT_MODE:
      if (not self.mode[1] and x != STNT_PROP or self.mode[1] and x == STNT_PROP):
        fmterr()
        return True
      submode(x,STNT_ATTR)
      return True
    elif self.mode[0] == Mode.ALRT.value and x in ALRT_MODE:
      if (not self.mode[1] and x != ALRT_PATH or self.mode[1] and x == ALRT_PATH):
        fmterr()
        return True
      submode(x,ALRT_ATTR)
      if self.mode[1] == ALRT_RECI:
        self.req_reci = True
      return True
    elif (self.mode[0] == Mode.SKIP.value and
         (x in PRIM_MODE or x in STNT_MODE or x in ALRT_MODE)):
      log.debug_l(f'エラー検知中のためサブモード[{x}]はスキップします')
      return True
    x = MODE.get(x)
    if not x:
      log.fmterr_l(f'「{csvl[HDR_POS]}」({pos2clm(HDR_POS)})は無効な表ヘッダです')
      return False
    self.mode = (x,None)
    log.debug_l(f'処理モードを[{self.mode[0]}]にセットしました')
    self.pcr,self.attrd,self.xr,self.xc,self.req_reci = [],{},None,None,False
    return True

  '''
    列ヘッダ解析
    [引数]
      csvl  : CSVファイル1行分のリスト
      clmd  : 列情報([列名: 列番号])を保持する辞書
      RIl   : resourceItem列(番号)を保持するリスト
    [戻り値]
      True  : OK
      False : NG
  '''
  def parse_clm(self,csvl,clmd,RIl):
    def is_RI(clm):
      return (self.mode[0] == Mode.RSCS.value and clm == 'resourceitem')
    def fmterr(k,x,lpc,start,no):
      while list(range(lpc)):
        i = clml.index(k,start)
        if no == 1:
          log.fmterr_l(f"'{k}'列が複数設定されています({pos2clm(x)}と{pos2clm(i)})")
        elif no == 2:
          log.warn_l(f'「{csvl[i]}」({pos2clm(i)})は無効な列です')
        start = i+1
        lpc -= 1
    global skipflg; skipflg = False
    if self.mode in [(Mode.PRIM.value,None),(Mode.STNT.value,None),(Mode.ALRT.value,None)]:
      log.fmterr_l(self.msg_inval_fmt(TBLN[self.mode[0]]))
      self.skip_mode()
      return True
    clml = csvl[:]
    rql = RQCLM[self.mode][:]
    for (i,x) in [(i,x) for (i,x) in enumerate(csvl) if i > HDR_POS and x]:
      clm = x.lower()
      if is_RI(clm):
        RIl.append(i)
      elif (self.mode[1] == PRIM_OPER and clm not in RQCLM[self.mode] or
            self.mode[1] == STNT_OPER and clm not in RQCLM[self.mode]):
        rql.append(x)
        clm = x
      if clm not in clmd:
        clmd[clm] = i
      clml[i] = clm
    for x in [x for x in rql if x not in clmd]:
      log.fmterr_l(f"'{x}'列が設定されていません")
    l = dict2list(clmd)
    for (k,x,cnt) in [(k,x,clml.count(k)) for (k,x) in l if clml.count(k) > 1]:
      if k in rql and not is_RI(k):
        fmterr(k,x,cnt-1,x+1,1)
    for (k,x,cnt) in [(k,x,clml.count(k)) for (k,x) in l if k not in rql]:
      fmterr(k,x,cnt,x,2)
      del clmd[k]  # 不要な列
    if self.mode[0] == Mode.RSCS.value:
      if skipflg:
        return False
      if RIl[0] < clmd['id'] < RIl[len(RIl)-1]:
        log.fmterr_l(self.msg_inval_fmt(TBLN[self.mode[0]]))
        return False
      del clmd['resourceitem']
    self.skip_mode(skipflg)
    return True

  '''
    有効データの有無チェック
    [引数]
      csvl  : CSVファイル1行分のリスト
      clmd  : 列情報([列名: 列番号])を保持する辞書
      RIl   : resourceItem列(番号)を保持するリスト
    [戻り値]
      True  : 有効なデータあり
      False : 有効なデータなし
  '''
  def chk_data(self,csvl,clmd=None,RIl=None):
    if clmd:
      # 実データの列数が列ヘッダのそれより少ない場合
      while list(range((max(clmd.values())+1) - len(csvl))):
        csvl.append('')  # 不足分
      if [x for x in list(clmd.values()) if csvl[x]] or [x for x in RIl if csvl[x]]:
        return True
      log.debug_l('実データが設定されていません')
      return False
    else:
      if not csvl:
        log.debug_l('改行のみの行です')
        return False
      elif csvl[0]:
        if csvl[0].startswith('#'):
          log.debug_l('コメントの行です')
          return False
        log.debug_l(f'{pos2clm(HDR_POS-1)}に「#」以外から始まる文字列が設定されています')
      if len(csvl) == csvl.count('') or len(csvl) <= HDR_POS:
        log.debug_l('データなし行です')
        return False
      return True

  def fmt_bool(self,x):
    from distutils.util import strtobool
    try:
      return 'true' if strtobool(x) else 'false'
    except Exception:
      pass
    return x

  def fmt_score(self,x):
    return x.lower().replace('infinity','INFINITY').replace('inf','INFINITY') \
      if x and re.fullmatch(r'[+-]?(inf|infinity)',x,flags=re.I) is not None else x

  def fmt_kind(self,x):
    return x.capitalize() \
      if x and re.fullmatch(r'(Optional|Mandatory|Serialize)',x,flags=re.I) is not None else x

  '''
    CIB・PCSファイル生成(【CSV】->【XML】->【ローカルcib.xml・pcsスクリプト】)
    1.【CSV】データを「全て」読み込んで、【XML】形式にして保持
    2.【XML】から【pcsコマンド】を生成、実行し【ローカルcib.xml】を出力
    [引数]
      なし
    [戻り値]
      RC.SUCCESS        : 成功
      RC.ERROR          : エラー発生 -> 処理は中止
      RC.ERROR_NONFATAL : エラー発生 -> 処理は完走
      RC.WARN           : 警告発生
  '''
  def main(self):
    log.debug('CIB・PCSファイル出力処理を開始します')
    if self.read_csv() == RC.ERROR:
      return RC.ERROR
    if self.root.hasChildNodes():
      self.xml_debug()
      log.debug('[ XML -> CIB・PCSファイル ]処理を開始します')
      s = self.xml2pcs()
      if not s:
        return RC.ERROR
      if not self.write_pcs(s):
        return RC.ERROR
      os.chmod(self.outsh,0o744)
    else:
      log.fmterr_l('有効なデータが設定されていません')
    log.debug('CIB・PCSファイル出力処理を終了します')
    if errflg:
      return RC.ERROR_NONFATAL
    if warnflg:
      return RC.WARN
    return RC.SUCCESS

  '''
   【CSV】データを「全て」読み、【XML】形式で保持
    [引数]
      なし
    [戻り値]
      RC.SUCCESS        : 成功
      RC.ERROR          : エラー発生
  '''
  def read_csv(self):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
      try:
        with open(self.input,'rb') as f:
          from chardet.universaldetector import UniversalDetector
          d = UniversalDetector()
          for l in f:
            d.feed(l)
            if d.done:
              break
          d.close()
          enc = d.result['encoding']
          log.debug(f'CSVファイルの文字コード [{enc}]')
      except Exception as e:
        log.innererr('CSVファイルの読み込みに失敗しました',e)
        return RC.ERROR
      if not enc:
        log.error('CSVファイルの文字コード判定に失敗しました')
        return RC.ERROR
      log.debug('[ CSV -> XML ]処理を開始します')
      with open(self.input,mode='r',newline='',encoding=enc) as f:
        import csv
        try:
          r = csv.reader(f)
          for csvlr in r:
            self.lno = log.lno = self.lno + 1
            for (i,x) in [(i,x) for (i,x) in enumerate(csvlr) if x]:
              csvlr[i] = re.sub(r'\r\n|\r',r'\n',x)
            csvl = csvlr[:]
            fmt_item(csvl,True)
            fmt_item(csvlr,False)
            if not self.chk_data(csvl):
              continue
            ''' 表ヘッダ解析 '''
            if csvl[HDR_POS]:
              log.debug_l('表ヘッダ解析処理を開始します')
              if not self.parse_hdr(csvl):
                break
              clmd,RIl = {},[]
              if not self.mode[1]:
                continue
            if self.mode[0] == Mode.SKIP.value:
              log.debug_l('次の表ヘッダ行までスキップします')
              continue
            ''' 列ヘッダ解析 '''
            if self.mode[0] and not clmd:
              log.debug_l('列ヘッダ解析処理を開始します')
              if not self.parse_clm(csvl,clmd,RIl):
                break
              continue
            ''' 実データ解析 '''
            if not self.mode[0]:
              log.fmterr_l('表ヘッダが設定されていません')
              return RC.ERROR
            if not self.chk_data(csvl,clmd,RIl):
              continue
            if not self.csv2xml(clmd,RIl,csvl,csvlr):
              break
        except Exception as e:
          log.innererr('CSVファイルの読み込みに失敗しました',e)
          return RC.ERROR
      # __with open(self.input,mode='r',newline='',encoding=enc) as f:
    # __with tempfile.TemporaryDirectory() as d:
    if not errflg:
      self.xml_chk_resources()
      self.xml_chk_location_rule()
    if errflg:
      self.xml_debug()
      return RC.ERROR
    return RC.SUCCESS

  def csv2xml(self,clmd,RIl,csvl,csvlr):
    x = self.mode[0]
    log.debug_l(f'{TBLN[x]}のデータを処理します')
    if x == Mode.CNFG.value:   self.debug_input(clmd,RIl,csvlr)
    else:                      self.debug_input(clmd,RIl,csvl)
    if   x == Mode.NODE.value: self.skip_mode(not self.c2x_node(clmd,csvl))
    elif x == Mode.PROP.value:                    self.c2x_option(Mode.PROP.value,clmd,csvl)
    elif x == Mode.RDEF.value:                    self.c2x_option(Mode.RDEF.value,clmd,csvl)
    elif x == Mode.ODEF.value:                    self.c2x_option(Mode.ODEF.value,clmd,csvl)
    elif x == Mode.RSCS.value:             return self.c2x_resources(clmd,RIl,csvl)
    elif x == Mode.ATTR.value: self.skip_mode(not self.c2x_attributes(clmd,csvl))
    elif x == Mode.PRIM.value: self.skip_mode(not self.c2x_primitive(clmd,csvl))
    elif x == Mode.STNT.value: self.skip_mode(not self.c2x_stonith(clmd,csvl))
    elif x == Mode.STLV.value: self.skip_mode(not self.c2x_stonith_lv(clmd,csvl))
    elif x == Mode.LOCN.value: self.skip_mode(not self.c2x_location_node(clmd,csvl))
    elif x == Mode.LOCR.value: self.skip_mode(not self.c2x_location_rule(clmd,csvl))
    elif x == Mode.COLO.value:                    self.c2x_colocation(clmd,csvl)
    elif x == Mode.ORDR.value:                    self.c2x_order(clmd,csvl)
    elif x == Mode.ALRT.value: self.skip_mode(not self.c2x_alert(clmd,csvl))
    elif x == Mode.CNFG.value:                    self.c2x_config(clmd,csvlr)
    return True

  '''
    クラスタ・ノード表データのXML化
    [引数]
      clmd  : 列情報([列名: 列番号])を保持する辞書
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_node(self,clmd,csvl):
    global skipflg; skipflg = False
    uname = csvl[clmd['uname']]
    if uname:
      self.attrd = {}; self.attrd['uname'] = uname
    else:
      uname = self.attrd.get('uname')
      if not uname:
        log.fmterr_l(self.msg_no_data('uname'))
    #
    # <csv>
    #  <{Mode.NODE}s>
    #   <{Mode.NODE} uname="pm01">
    #    <attribute>
    #     <nv name="standby" value="on"/>
    #      :
    #    <utilization>
    #     <nv name="capacity" value="1"/>
    #      :
    #
    x = self.xml_get_node(self.root,f'{Mode.NODE.value}s')
    y = self.xml_get_nodes(x,Mode.NODE.value,'uname',uname)
    if y:
      node = y[0]
    else:
      node = self.xml_create_child(x,Mode.NODE.value)
      node.setAttribute('uname',uname)
    self.c2x_attributes(clmd,csvl,node,NODE_ATTR_TYPE)
    return False if skipflg else True

  '''
    クラスタ・プロパティ、リソース/オペレーション・デフォルト表データのXML化
    [引数]
      tag   : データ(<nv .../>)を追加するNodeのタグ名
      clmd  : 列情報([列名: 列番号])を保持する辞書
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_option(self,tag,clmd,csvl):
    global skipflg; skipflg = False
    name = csvl[clmd['name']]
    value = csvl[clmd['value']]
    self.xml_chk_nv(self.root,tag,name,value)
    if skipflg:
      return False
    #
    # <csv>
    #  <{Mode.PROP}>
    #   <nv name="no-quorum-policy" value="ignore"/>
    #    :
    #  <{Mode.RDEF}>
    #   <nv name="resource-stickiness" value="200"/>
    #    :
    #  <{Mode.ODEF}>
    #   <nv name="record-pending" value="false"/>
    #    :
    #
    return self.xml_append_nv(self.xml_get_node(self.root,tag),name,value)

  '''
    リソース構成表データのXML化
    [引数]
      clmd  : 列情報([列名: 列番号])を保持する辞書
      RIl   : resourceItem列(番号)を保持するリスト
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_resources(self,clmd,RIl,csvl):
    global skipflg; skipflg = False
    pos = 0
    x = [x for x in RIl if csvl[x]]
    if len(x) == 0:
      log.fmterr_l(self.msg_no_data('resourceItem'))
    elif len(x) > 1:
      log.fmterr_l(self.msg_disca_data("複数の'resourceItem'列"))
    elif not RSC_TYPE.get(csvl[x[0]].lower()):
      log.fmterr_l(self.msg_inval_data('resourceItem',csvl[x[0]],RSC_TYPE.keys()))
    else:
      pos = x[0]
      ri = csvl[pos].lower()
    depth = -1
    if pos > 0:
      if self.pcr:
        for i in [i for (i,x) in enumerate(RIl[:len(self.pcr)+1]) if x == pos]:
          depth = i
      elif csvl[RIl[0]]:
        depth = 0
    if pos > 0 and depth == -1:
      log.fmterr_l("'resourceItem'列 (リソース構成) の設定に誤りがあります")
    elif depth > 0:
      p_rt,p_id = self.pcr[depth-1]
      # primitive|stonith  - (doesn't contain a resource)
      # group              - {primitive|stonith}
      # clone|promotable   - {primitive|stonith|group}
      if (p_rt == 'primitive' or p_rt == 'stonith' or
          p_rt == 'group' and (ri != 'primitive' and ri != 'stonith') or
          p_rt in ['clone','promotable'] and ri not in ['primitive','stonith','group']):
        log.fmterr_l("リソース種別('resourceItem'列)の設定に誤りがあります")
    id = csvl[clmd['id']]
    if not id:
      log.fmterr_l(self.msg_no_data('id'))
    elif self.rr:
      for x in [x for x in self.rr.childNodes if x.getAttribute('id') == id]:
        log.fmterr_l(self.msg_dup_set(f'「id: {id}」','リソース',x.getAttribute(ATTR_C)))
    if skipflg:
      return False
    #
    # <csv>
    #  <{Mode.RSCS}>
    #   <{Mode.PRIM} id="dummy1"/>
    #   <{Mode.GRUP} id="dummy-group">
    #    <rsc id="dummy2"/>
    #    <rsc id="dummy3"/>
    #   </{Mode.GRUP}>
    #   <{Mode.PRIM} id="dummy2"/>
    #   <{Mode.PRIM} id="dummy3"/>
    #   <{Mode.CLNE} id="dummy-clone">
    #    <rsc id="dummy"/>
    #   </{Mode.CLNE}>
    #   <{Mode.PRIM} id="dummy"/>
    #   <{Mode.PROM} id="stateful-clone">
    #    <rsc id="stateful"/>
    #   </{Mode.PROM}>
    #   <{Mode.PRIM} id="stateful"/>
    #   <{Mode.GRUP} id="fence1-group">
    #    <rsc id="fence1-kdump"/>
    #    <rsc id="fence1-ipmilan"/>
    #   </{Mode.GRUP}>
    #   <{Mode.STNT} id="fence1-kdump"/>
    #   <{Mode.STNT} id="fence1-ipmilan"/>
    #  </{Mode.RSCS}>
    #
    if not self.rr:
      self.rr = self.xml_create_child(self.root,Mode.RSCS.value)
    # 「<{Mode.PRIM}|{Mode.STNT}|{Mode.GRUP}|{Mode.CLNE}|{Mode.PROM} id="xxx"/>」を追加
    x = self.xml_create_child(self.rr,RSC_TYPE[ri])
    x.setAttribute('id',id)
    x.setAttribute(ATTR_C,str(self.lno))
    del self.pcr[depth:]
    self.pcr.append((ri,id))
    log.debug1_l(f'リソースの親子関係: + {self.pcr}')
    if depth == 0:
      return True
    # 親子関係である場合は「<{Mode.GRUP}|{Mode.CLNE}|{Mode.PROM}>」の子として、
    x = self.xml_get_nodes(self.rr,RSC_TYPE[p_rt],'id',p_id)[0]
    # 「<rsc id="yyy"/>」を追加
    x = self.xml_create_child(x,'rsc')
    x.setAttribute('id',id)
    x.setAttribute(ATTR_C,str(self.lno))
    return True

  '''
    リソース構成パラメータ表データのXML化
    [引数]
      clmd  : 列情報([列名: 列番号])を保持する辞書
      csvl  : CSVファイル1行分のリスト
      node  : データ(<options>|<meta>|<utilization>...)を追加するNode
              * Primitive表とSTONITHリソース表の場合に指定される
      typs  : 設定可能なパラメータ種別
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_attributes(self,clmd,csvl,node=None,typs=None):
    global skipflg
    if node:
      type = csvl[clmd['type']].lower()
      if type:
        if type in typs:
          self.attrd['type'] = type
        else:
          log.fmterr_l(self.msg_inval_data('type',csvl[clmd['type']],typs))
      else:
        type = self.attrd.get('type')
        if not type:
          log.fmterr_l(self.msg_no_data('type'))
    else:
      skipflg = False
      id = csvl[clmd['id']]
      if id:
        self.attrd['id'] = id
      else:
        id = self.attrd.get('id')
        if not id:
          log.fmterr_l(self.msg_no_data('id'))
      node = self.xml_get_rscnode(id)
      type = ELSE_ATTR_TYPE[0]
    name = csvl[clmd['name']]
    value = csvl[clmd['value']]
    #
    # 'pcs resource utilization ...' :「name1=v1」「name1=v2」の指定方法と重複チェック
    #
    # (1) コマンドを分けた場合は、上書き ※重複チェック無し
    # $ pcs --version
    # 0.10.1
    # $ pcs resource utilization dummy1 capacity=1
    # $ pcs resource utilization dummy1 capacity=2 ; echo $?
    # 0
    #
    # (2) １コマンドの場合は、重複エラー ※重複チェックあり
    # $ pcs resource utilization dummy1 capacity=1 capacity=2
    # Error: duplicate option 'capacity' with different values '1' and '2'
    #
    # -> (1)方式で出力・実行するので、設定が重複していないかここでチェック
    #
    # ※'pcs resource create ...'の"option (resource,meta)"は重複チェックあり
    # $ pcs resource create dummy1 Dummy fake=v1 fake=v2
    # Error: duplicate option 'fake' with different values 'v1' and 'v2'
    # $ pcs resource create dummy1 Dummy meta m1=v1 m1=v2
    # Error: duplicate option 'm1' with different values 'v1' and 'v2'
    #
    self.xml_chk_nv(node,type,name,value,True if type == 'utilization' else False)
    if skipflg:
      return False
    #
    # <csv>
    #  <{Mode.RSCS}>
    #   <{Mode.PRIM} id="dummy" ...>
    #    <options>
    #     <nv name="op_sleep" value="10"/>
    #      :
    #    <meta>
    #     <nv name="migration-threshold" value="0"/>
    #      :
    #    <utilization>
    #     <nv name="capacity" value="1"/>
    #      :
    #   <{Mode.PROM} id="stateful-clone">
    #    <rsc id="stateful"/>
    #    <meta>
    #     <nv name="promoted-max" value="1"/>
    #      :
    #
    x = self.xml_get_node(node,type)
    if not x.getAttribute(ATTR_C):
      x.setAttribute(ATTR_C,str(self.lno))
    return self.xml_append_nv(x,name,value)

  '''
    Primitiveリソース表データのXML化
    [引数]
      clmd  : 列情報([列名: 列番号])を保持する辞書
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_primitive(self,clmd,csvl):
    global skipflg; skipflg = False
    if self.mode[1] == PRIM_PROP and not self.xr:
      id = csvl[clmd['id']]
      if id:
        self.xr = self.xml_get_rscnode(id,Mode.PRIM.value)
        if self.xr and self.xr.getAttribute(ATTR_U):
          log.fmterr_l(
            self.msg_dup_set(f'「id: {id}」',TBLN[self.mode[0]],self.xr.getAttribute(ATTR_U)))
        elif self.xr:
          self.xr.setAttribute(ATTR_U,str(self.lno))
      else:
        log.fmterr_l(self.msg_no_data('id'))
      if not csvl[clmd['type']]:
        log.fmterr_l(self.msg_no_data('type'))
    elif self.mode[1] == PRIM_PROP:
      log.fmterr_l(self.msg_inval_fmt(TBLN[self.mode[0]]))
    elif self.mode[1] != PRIM_PROP and not self.xr:
      log.fmterr_l("'id'列に値が設定されていません")
    elif self.mode[1] == PRIM_OPER:
      type = csvl[clmd['type']]
      if not type:
        log.fmterr_l(self.msg_no_data('type'))
    if skipflg:
      return False
    #
    # <csv>
    #  <{Mode.RSCS}>
    #   <{Mode.PRIM} class="ocf" id="dummy1" provider="pacemaker" type="Dummy">
    #    <options/>
    #    <meta/>
    #    <utilization/>
    #    <op>
    #     <start>
    #      <nv name="timeout" value="60s"/>
    #       :
    #     </start>
    #     <monitor>
    #      :
    #
    if self.mode[1] == PRIM_PROP:
      for x in [x for x in RQCLM[self.mode] if csvl[clmd[x]]]:
        self.xr.setAttribute(x,csvl[clmd[x]])
    elif self.mode[1] == PRIM_ATTR:
      return self.c2x_attributes(clmd,csvl,self.xr,PRIM_ATTR_TYPE)
    elif self.mode[1] == PRIM_OPER:
      o = self.xml_create_child(self.xml_get_node(self.xr,'op'),type)
      for (k,x) in list(clmd.items()):
        if k in RQCLM[self.mode] or not csvl[x]:
          continue
        self.xml_append_nv(o,k,csvl[x])
    return True

  '''
    STONITHリソース表データのXML化
    [引数]
      clmd  : 列情報([列名: 列番号])を保持する辞書
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_stonith(self,clmd,csvl):
    global skipflg; skipflg = False
    if self.mode[1] == STNT_PROP and not self.xr:
      id = csvl[clmd['id']]
      if id:
        self.xr = self.xml_get_rscnode(id,Mode.STNT.value)
        if self.xr and self.xr.getAttribute(ATTR_U):
          log.fmterr_l(
            self.msg_dup_set(f'「id: {id}」',TBLN[self.mode[0]],self.xr.getAttribute(ATTR_U)))
        elif self.xr:
          self.xr.setAttribute(ATTR_U,str(self.lno))
      else:
        log.fmterr_l(self.msg_no_data('id'))
      if not csvl[clmd['type']]:
        log.fmterr_l(self.msg_no_data('type'))
    elif self.mode[1] == STNT_PROP:
      log.fmterr_l(self.msg_inval_fmt(TBLN[self.mode[0]]))
    elif self.mode[1] != STNT_PROP and not self.xr:
      log.fmterr_l("'id'列に値が設定されていません")
    elif self.mode[1] == STNT_OPER:
      type = csvl[clmd['type']]
      if not type:
        log.fmterr_l(self.msg_no_data('type'))
    if skipflg:
      return False
    #
    # <csv>
    #  <{Mode.RSCS}>
    #   <{Mode.STNT} id="fence1-ipmilan" type="fence_ipmilan">
    #    <options/>
    #    <meta/>
    #    <op>
    #     <start>
    #      <nv name="timeout" value="60s"/>
    #       :
    #     <monitor>
    #      :
    #
    if self.mode[1] == STNT_PROP:
      for x in [x for x in RQCLM[self.mode] if csvl[clmd[x]]]:
        self.xr.setAttribute(x,csvl[clmd[x]])
    elif self.mode[1] == STNT_ATTR:
      return self.c2x_attributes(clmd,csvl,self.xr,STNT_ATTR_TYPE)
    elif self.mode[1] == STNT_OPER:
      o = self.xml_create_child(self.xml_get_node(self.xr,'op'),type)
      for (k,x) in list(clmd.items()):
        if k in RQCLM[self.mode] or not csvl[x]:
          continue
        self.xml_append_nv(o,k,csvl[x])
    return True

  '''
    STONITHの実行順序表データのXML化
    [引数]
      clmd  : 列情報([列名: 列番号])を保持する辞書
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_stonith_lv(self,clmd,csvl):
    global skipflg; skipflg = False
    node = csvl[clmd['node']]
    if node:
      self.attrd = {}; self.attrd['node'] = node
    else:
      node = self.attrd.get('node')
      if not node:
        log.fmterr_l(self.msg_no_data('node'))
    id = csvl[clmd['id']]
    if not id:
      log.fmterr_l(self.msg_no_data('id'))
    level = csvl[clmd['level']]
    if not level:
      log.fmterr_l(self.msg_no_data('level'))
    #
    # 'pcs stonith level add ...'では設定対象のSTONITHリソースの有無に関係なく、
    # "Warning: Stonith resource(s) '<STONITH>' do not exist"が出力される
    # -> STONITHリソースが設定されているか、ここでチェック
    #
    # $ pcs --version
    # 0.10.1
    # $ pcs stonith level add 1 pm01 fence1-kdump --force
    # Warning: Stonith resource(s) 'fence1-kdump' do not exist
    # $ pcs stonith level add 1 pm01 DOES_NOT_EXIST --force
    # Warning: Stonith resource(s) 'DOES_NOT_EXIST' do not exist
    #
    self.xml_get_rscnode(id,Mode.STNT.value)
    if skipflg:
      return False
    #
    # <csv>
    #  <{Mode.STLV}s>
    #   <{Mode.STLV} id="fence1-kdump" level="1" node="pm01"/>
    #   <{Mode.STLV} id="fence1-ipmilan" level="2" node="pm01"/>
    #    :
    #
    l = self.xml_create_child(
          self.xml_get_node(self.root,f'{Mode.STLV.value}s'),
          Mode.STLV.value)
    if node:
      l.setAttribute('node',node)
    l.setAttribute('id',id)
    l.setAttribute('level',level)
    l.setAttribute(ATTR_C,str(self.lno))
    return True

  '''
    リソース配置制約(ノード)表データのXML化
    [引数]
      clmd  : 列情報([列名: 列番号])を保持する辞書
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_location_node(self,clmd,csvl):
    global skipflg; skipflg = False
    rsc = csvl[clmd['rsc']]
    if rsc:
      self.attrd = {}; self.attrd['rsc'] = rsc
    else:
      rsc = self.attrd.get('rsc')
      if not rsc:
        log.fmterr_l(self.msg_no_data('rsc'))
    #
    # 'pcs constraint location <id> prefers|avoids ...'で"prefers|avoids"以外を
    # 指定した場合、Error等ではなくUsageが出力される (Usageではユーザに不親切)
    # -> "prefers|avoids"か、ここでチェック
    #
    # $ pcs --version
    # 0.10.1
    # $ pcs constraint location dummy1 Prefers pm01
    #
    # Usage: pcs constraint [constraints]...
    #     location <resource> prefers <node>[=<score>] [<node>[=<score>]]...
    #  :
    #     location <resource> avoids <node>[=<score>] [<node>[=<score>]]...
    #  :
    #
    preavo = csvl[clmd['prefers/avoids']].lower()
    if preavo:
      if preavo not in LOC_NODE_PREAVO:
        log.fmterr_l(self.msg_inval_data('prefers/avoids',preavo,LOC_NODE_PREAVO))
      else:
        self.attrd['preavo'] = preavo
    else:
      preavo = self.attrd.get('preavo')
      if not preavo:
        log.fmterr_l(self.msg_no_data('prefers/avoids'))
    node = csvl[clmd['node']]
    if not node:
      log.fmterr_l(self.msg_no_data('node'))
    #
    # 'pcs constraint location ... <score>'で指定可能な"score"は「整数|[-]INFINITY」
    # -> 「INFINITY|-INFINITY」に変換しておく
    #
    # $ pcs --version
    # 0.10.1
    # $ pcs constraint location dummy1 prefers pm01=inf
    # Error: invalid score 'inf', use integer or INFINITY or -INFINITY
    #
    score = self.fmt_score(csvl[clmd['score']])
    if skipflg:
      return False
    #
    # <csv>
    #  <{Mode.LOCN}s>
    #   <{Mode.LOCN} rsc="dummy1">
    #    <avoids>
    #     <exp node="pm02"/>
    #      :
    #   <{Mode.LOCN} rsc="dummy-group">
    #    <prefers>
    #     <exp node="pm01" score="200"/>
    #     <exp node="pm02" score="100"/>
    #      :
    #
    x = self.xml_get_node(self.root,f'{Mode.LOCN.value}s')
    y = self.xml_get_nodes(x,Mode.LOCN.value,'rsc',rsc)
    if y:
      x = y[0]
    else:
      x = self.xml_create_child(x,Mode.LOCN.value)
      x.setAttribute('rsc',rsc)
    if x.getElementsByTagName(preavo):
      x = x.getElementsByTagName(preavo)[0]
    else:
      x = self.xml_create_child(x,preavo)
      x.setAttribute(ATTR_C,str(self.lno))
    #
    # 'pcs constraint location <id> prefers|avoids ...'では設定の重複チェックは無し
    #  (設定は無条件・無警告で上書きされる)
    # -> 設定が重複していないか、ここでチェック
    #
    # $ pcs --version
    # 0.10.1
    # $ pcs constraint location dummy1 prefers pm01
    # Warning: Validation for node existence in the cluster will be skipped
    # $ pcs constraint location dummy1 prefers pm01=200
    # Warning: Validation for node existence in the cluster will be skipped
    #
    # * "Warning: Validation for node ..."はフィルタリング対象 (CONFファイル参照)
    #
    if self.xml_get_nodes(x,'exp','node',node):
      log.warn_l(
        self.msg_dup_set(f'「{rsc}, {preavo}, {node}」','リソース配置制約',x.getAttribute(ATTR_C)))
    x = self.xml_create_child(x,'exp')
    x.setAttribute('node',node)
    if score:
      x.setAttribute('score',score)
    x.setAttribute(ATTR_C,str(self.lno))
    return True

  '''
    リソース配置制約表(ルール)データのXML化
    [引数]
      clmd  : 列情報([列名: 列番号])を保持する辞書
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_location_rule(self,clmd,csvl):
    def c2x_attr(node,names,tag=None,set=False):
      r = None if tag else node
      for (k,x) in [(k,x) for (k,x) in list(clmd.items()) if k in names and csvl[x]]:
        if not r:
          r = self.xml_create_child(node,tag)
        r.setAttribute(k,csvl[x])
        set = True
      if set:
        r.setAttribute(ATTR_C,str(self.lno))
    global skipflg; skipflg = False
    rsc = csvl[clmd['rsc']]
    if rsc:
      self.attrd = {}; self.attrd['rsc'] = rsc
    else:
      rsc = self.attrd.get('rsc')
      if not rsc:
        log.fmterr_l(self.msg_no_data('rsc'))
    #
    # 'pcs constraint location ... <score>'で指定可能な"score"は「整数|[-]INFINITY」
    # -> 「INFINITY|-INFINITY」に変換しておく
    #
    # $ pcs --version
    # 0.10.1
    # $ pcs constraint location dummy1 rule score=-inf not_defined pgsql-status
    # Warning: invalid score '-inf', setting score-attribute=pingd instead
    #
    x,r = self.fmt_score(csvl[clmd['score']]),None
    if x:
      csvl[clmd['score']] = self.attrd['score'] = x
      r = self.doc.createElement('rule')
    else:
      if not self.attrd.get('score'):
        log.fmterr_l(self.msg_no_data('score'))
      else:
        if csvl[clmd['bool_op']]:
          log.warn_l(self.msg_disca_data("'bool_op'列"))
        if csvl[clmd['role']]:
          log.warn_l(self.msg_disca_data("'role'列"))
        csvl[clmd['score']] = self.attrd['score']
    if not csvl[clmd['attribute']]:
      log.fmterr_l(self.msg_no_data('attribute'))
    if csvl[clmd['op']]:
      if csvl[clmd['op']].lower() in LOC_RULE_UNARY:
        if csvl[clmd['value']]:
          log.warn_l(self.msg_disca_data("'value'列"))
      else:
        if not csvl[clmd['value']]:
          log.fmterr_l(self.msg_no_data('value'))
    else:
      log.fmterr_l(self.msg_no_data('op'))
    #
    # 'pcs constraint location <id> rule role=...'で指定可能な"role"は小文字のみ
    # -> 小文字に変換しておく
    #
    # $ pcs --version
    # 0.10.1
    # $ pcs constraint location stateful-clone rule role=Master
    # Error: invalid role 'Master', use 'master' or 'slave'
    #
    csvl[clmd['role']] = csvl[clmd['role']].lower()
    if skipflg:
      return False
    #
    # <csv>
    #  <{Mode.LOCR}s>
    #   <{Mode.LOCR} rsc="stateful-clone">
    #    <rule bool_op="and" role="master" score="INFINITY">
    #     <exp attribute="ping-status" op="lt" value="1"/>
    #     <exp attribute="ping-status" op="not_defined"/>
    #      :
    #
    x = self.xml_get_node(self.root,f'{Mode.LOCR.value}s')
    l = self.xml_get_nodes(x,Mode.LOCR.value,'rsc',rsc)
    if l:
      l = l[0]
    else:
      l = self.doc.createElement(Mode.LOCR.value)
      l.setAttribute('rsc',rsc)
      x.appendChild(l)
    if r:
      x = self.xml_get_nodes(x,'rule',ATTR_S,'working')
      if x:
        x[0].removeAttribute(ATTR_S)
      r.setAttribute(ATTR_S,'working')
      c2x_attr(r,['score','bool_op','role'])
      l.appendChild(r)
    x = self.xml_get_nodes(l,'rule',ATTR_S,'working')[0]
    if x.getElementsByTagName('exp') and not x.getAttribute('bool_op'):
      log.fmterr_l(self.msg_no_data('bool_op'),x.getAttribute(ATTR_C))
      return False
    c2x_attr(x,['attribute','op','value'],'exp')
    return True

  '''
    リソース同居制約表データのXML化
    [引数]
      clmd  : 列情報([列名: 列番号])を保持する辞書
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_colocation(self,clmd,csvl):
    global skipflg; skipflg = False
    for x in [x for x in ['rsc','with-rsc','score'] if not csvl[clmd[x]]]:
      log.fmterr_l(self.msg_no_data(x))
    #
    # 'pcs constraint colocation ...'で指定可能な"score"は「整数|[-]INFINITY」に見える
    # -> 「INFINITY|-INFINITY」に変換しておく
    #
    # $ pcs --version
    # 0.10.1
    #
    # $ pcs constraint colocation add dummy1 with dummy2 score=INF
    # Error: Unable to update cib
    #  :
    # Call failed: Update does not conform to the configured schema
    #
    # $ pcs constraint colocation add dummy1 with dummy2 score=infinity
    # Error: Unable to update cib
    #  :
    # Call failed: Update does not conform to the configured schema
    #
    csvl[clmd['score']] = self.fmt_score(csvl[clmd['score']])
    if skipflg:
      return False
    #
    # <csv>
    #  <{Mode.COLO}s>
    #   <{Mode.COLO} rsc="dummy-group" rsc-role="started" score="INFINITY"
    #     with-rsc="stateful-clone" with-rsc-role="master"/>
    #    :
    #
    c = self.xml_create_child(
          self.xml_get_node(self.root,f'{Mode.COLO.value}s'),
          Mode.COLO.value)
    for (k,x) in [(k,x) for (k,x) in list(clmd.items()) if csvl[x]]:
      c.setAttribute(k,csvl[x])
    c.setAttribute(ATTR_C,str(self.lno))
    return True

  '''
    リソース起動順序制約表データのXML化
    [引数]
      clmd  : 列情報([列名: 列番号])を保持する辞書
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_order(self,clmd,csvl):
    def chk_action(clm,x):
      if x:
        if x.lower() in ORDR_ACTION:
          return x.lower()
        else:
          log.fmterr_l(self.msg_inval_data(f'{clm}',x,ORDR_ACTION))
      return x
    global skipflg; skipflg = False
    for x in [x for x in ['first-rsc','then-rsc'] if not csvl[clmd[x]]]:
      log.fmterr_l(self.msg_no_data(x))
    #
    # 'pcs constraint order ... 'で指定可能な"kind"は「Optional|Mandatory|Serialize」
    # -> capitalizeしておく
    #
    # $ pcs --version
    # 0.10.1
    # $ pcs constraint order stateful-clone then dummy-group kind=optional
    # Error: Unable to update cib
    #    1 <cib ...
    #    2   <configuration>
    #    3     <crm_config>
    #  :
    # Call failed: Update does not conform to the configured schema
    #
    csvl[clmd['kind']] = self.fmt_kind(csvl[clmd['kind']])
    #
    # 'pcs constraint order [action] ... 'で"start|promote|demote|stop"以外を
    # 指定した場合、Error等ではなくUsageが出力される (Usageではユーザに不親切)
    # -> "start|promote|demote|stop"か、ここでチェック
    #
    # $ pcs --version
    # 0.10.1
    # $ pcs constraint order Start stateful-clone then dummy-group
    #
    # Usage: pcs constraint [constraints]...
    #     order [show] [--full]
    #  :
    #     order [action] <resource id> then [action] <resource id> [options]
    #  :
    #
    csvl[clmd['first-action']] = chk_action('first-action',csvl[clmd['first-action']])
    csvl[clmd['then-action']] = chk_action('then-action',csvl[clmd['then-action']])
    #
    # 'pcs constraint order ... 'で指定可能な"symmetrical"は「true|false」
    # -> 「true|false」に変換しておく
    #
    # $ pcs --version
    # 0.10.1
    # $ pcs constraint order stateful-clone then dummy-group symmetrical=no
    # Error: invalid symmetrical value 'no', allowed values are: true, false
    #
    csvl[clmd['symmetrical']] = self.fmt_bool(csvl[clmd['symmetrical']])
    if skipflg:
      return False
    #
    # <csv>
    #  <{Mode.ORDR}s>
    #   <{Mode.ORDR} first-action="promote" first-rsc="stateful-clone" kind="Mandatory"
    #     symmetrical="false" then-action="start" then-rsc="dummy-group"/>
    #    :
    #
    o = self.xml_create_child(
          self.xml_get_node(self.root,f'{Mode.ORDR.value}s'),
          Mode.ORDR.value)
    for (k,x) in [(k,x) for (k,x) in list(clmd.items()) if csvl[x]]:
      o.setAttribute(k,csvl[x])
    o.setAttribute(ATTR_C,str(self.lno))
    return True

  '''
    Alert設定表データのXML化
    [引数]
      clmd  : 列情報([列名: 列番号])を保持する辞書
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_alert(self,clmd,csvl):
    global skipflg; skipflg = False
    #
    # <csv>
    #  <{Mode.ALRT}s>
    #   <{Mode.ALRT} path="/usr/share/pacemaker/alerts/alert_snmp.sh">
    #    <options>
    #     <nv name="trap_add_hires_timestamp_oid" value="false"/>
    #      :
    #    <meta>
    #     <nv name="kind" value="attribute"/>
    #      :
    #    <{Mode.AREC} value="192.168.xxx.xxx">
    #     <options/>
    #     <meta/>
    #      :
    #    <{Mode.AREC} value="192.168.yyy.yyy">
    #     :
    #
    x = self.xml_get_node(self.root,f'{Mode.ALRT.value}s')
    if self.mode[1] == ALRT_PATH:
      path = csvl[clmd['path']]
      if path:
        y = self.xml_get_nodes(x,Mode.ALRT.value,'path',path)
        if y:
          log.fmterr_l(self.msg_dup_set(f'「path: {path}」','alert',y[0].getAttribute(ATTR_C)))
        else:
          self.xr = self.xc = self.xml_create_child(x,Mode.ALRT.value)
          self.xr.setAttribute('path',path)
          self.xr.setAttribute(ATTR_C,str(self.lno))
    elif self.mode[1] == ALRT_ATTR:
      if not self.xr:
        log.fmterr_l("'path'列に値が設定されていません")
      if self.req_reci:
        log.fmterr_l("'recipient'列に値が設定されていません")
      if not skipflg:
        self.c2x_attributes(clmd,csvl,self.xc,ALRT_ATTR_TYPE)
    elif self.mode[1] == ALRT_RECI:
      to = csvl[clmd['recipient']]
      if to:
        if self.xr:
          self.xc = self.xml_create_child(self.xr,Mode.AREC.value)
          self.xc.setAttribute('value',to)
          self.xc.setAttribute(ATTR_C,str(self.lno))
          self.req_reci = False
        else:
          log.fmterr_l("'path'列に値が設定されていません")
    return False if skipflg else True

  '''
    追加設定表データのXML化
    [引数]
      clmd  : 列情報([列名: 列番号])を保持する辞書
      csvl  : CSVファイル1行分のリスト
    [戻り値]
      True  : OK
      False : NG(フォーマット・エラー)
  '''
  def c2x_config(self,clmd,csvl):
    l = csvl[clmd['config']].split('\n')
    for (i,x) in enumerate(l):
      l[i] = del_rblank(del_rblank(x).rstrip('\\'))
    #
    # <csv>
    #  <{Mode.CNFG}s>
    #   <{Mode.CNFG} data="..."/>
    #    :
    #
    c = self.xml_create_child(
          self.xml_get_node(self.root,f'{Mode.CNFG.value}s'),
          Mode.CNFG.value)
    c.setAttribute('data','\n'.join(l))
    c.setAttribute(ATTR_C,str(self.lno))
    return True

  def xml_get_node(self,node,tag):
    return node.getElementsByTagName(tag)[0] \
      if node.getElementsByTagName(tag) else self.xml_create_child(node,tag)

  def xml_create_child(self,node,tag):
    x = self.doc.createElement(tag)
    node.appendChild(x)
    return x

  '''
    name列とvalue列の値のチェック
    -> <node ...><tag><nv name="xxx" value="yyy"/>と追加する前にチェック
    [引数]
      node  : 追加対象のNode
      tag   : 追加対象のtag(attribute種別 {options|meta|...})
      name  : name列の値
      value : value列の値
      dup   : 重複チェックを行うか
    [戻り値]
      なし(結果はerrflg*を参照)
  '''
  def xml_chk_nv(self,node,tag,name,value,dup=True):
    if not name:
      log.fmterr_l(self.msg_no_data('name'))
    if not value:
      log.fmterr_l(self.msg_no_data('value'))
    if not node or not tag or not dup or not name:
      return
    for x in [x for y in self.xml_get_childs(node,[tag])
      for x in y.childNodes if x.getAttribute('name') == name]:
      log.warn_l(self.msg_dup_set("'name'列",f'値「{name}」',x.getAttribute(ATTR_C)))
      return

  def xml_append_nv(self,node,name,value):
    if not name and not value:
      return True
    x = self.xml_create_child(node,'nv')
    x.setAttribute('name',name)
    x.setAttribute('value',value)
    x.setAttribute(ATTR_C,str(self.lno))
    return True

  '''
    Node内から指定タグ名のNodeを取得
    [引数]
      node : 対象Node
      tags : 対象タグ名のリスト
    [戻り値]
      Nodeのリスト
  '''
  def xml_get_childs(self,node,tags):
    return [x for x in node.childNodes if x.nodeName in tags] if node else []

  '''
    <{Mode.RSCS}>から指定id(+指定タグ名)のNodeを取得
    -> <{Mode.RSCS}><aaa id="xxx"/></{Mode.RSCS}>からidがxxxの<aaa>を取得
    [引数]
      id  : 対象リソースのid
      tag : 対象タグ名
    [戻り値]
      not None : 指定idのNode
          None : Node特定できず
                 (-> 対象リソースがリソース構成表に設定されていない)
  '''
  def xml_get_rscnode(self,id,tag=None):
    if not id:
      return
    if self.rr:
      for x in [x for x in self.rr.childNodes if x.getAttribute('id') == id]:
        if tag and x.nodeName != tag:
          continue
        return x
    if not tag:
      tag = ''
    log.fmterr_l(
      f'「id: {id}」の{tag.capitalize()}リソースが{TBLN[Mode.RSCS.value]}に設定されていません')

  '''
    指定Nodeの全下位要素から指定タグ名かつ属性のNodeを取得
    [引数]
      node  : 対象Node
      tag   : 対象タグ名
      attr  : 対象属性名
      value : 対象属性値
    [戻り値]
      Nodeのリスト
  '''
  def xml_get_nodes(self,node,tag,attr,value):
    l = []
    if node:
      for x in [x for x in node.getElementsByTagName(tag) if x.getAttribute(attr) == value]:
        l.append(x)
    return l

  '''
    リソース構成表データのチェック
      ・リソース構成表の
        - 'primitive'に対し Primitiveリソース表が設定されているか
        - 'stonith'に対し STONITHリソース表が設定されているか
      ・'group'|'clone'|'promotable'にリソースが設定されているか
      ・clone ID|promotable IDのチェック
    [引数]
      なし
    [戻り値]
      なし(結果はerrflg*を参照)
  '''
  def xml_chk_resources(self):
    if not self.rr:
      return
    for x in self.rr.childNodes:
      id = x.getAttribute('id')
      if x.nodeName == Mode.PRIM.value:
        if not x.getAttribute(ATTR_U):
          log.fmterr_l(f'「id: {id}」の{TBLN[Mode.PRIM.value]}が設定されていません',
            x.getAttribute(ATTR_C))
      elif x.nodeName == Mode.STNT.value:
        if not x.getAttribute(ATTR_U):
          log.fmterr_l(f'「id: {id}」の{TBLN[Mode.STNT.value]}が設定されていません',
            x.getAttribute(ATTR_C))
      elif not self.xml_get_childs(x,['rsc']):
        log.fmterr_l(f'{x.nodeName}リソース「id: {id}」にリソースが設定されていません',
          x.getAttribute(ATTR_C))

  def xml_chk_location_rule(self):
    for x in [x for y in self.root.getElementsByTagName(Mode.LOCR.value)
      for x in y.childNodes]:
      if x.getAttribute('bool_op') and x.childNodes.length == 1:
        log.lno = x.getAttribute(ATTR_C)
        log.warn_l(self.msg_disca_data("'bool_op'列"))

  '''
    コマンドを実行
    [引数]
      cmd   : コマンド文字列
      lno   : (コマンドを生成した)CSVファイルの行番号
    [戻り値]
      True  : OK
      False : NG(実行エラー)
  '''
  def run_pcs(self,cmd,lno):
    def fmtmsg(output):
      return log.indent(f'$ {cmd}\n{output}')
    def error(output):
      if log.lv >= log.INFO: log.error(f'{m}')
      else:                  log.error_l(f'{m}')
      log.error_r(fmtmsg(output))
    def warn(output):
      if log.lv >= log.INFO: log.warn(f'{m}')
      else:                  log.warn_l(f'{m}')
      log.warn_r(fmtmsg(output))
    def info(output,msg=None):
      log.info('%s%s'%(m,(f' {msg}') if msg else ''))
      log.info_r(fmtmsg(output))
    def debug(output,msg=None):
      log.debug('%s%s'%(m,(f' {msg}') if msg else ''))
      log.debug_r(fmtmsg(output))
    try:
      log.lno = lno
      log.info_l(f'[コマンド_実行] {cmd}')
      m = '[コマンド_結果]'
      p = subprocess.run(shlex.split(cmd),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
      if p.returncode != 0:
        error(p.stderr.decode(U8) if p.stderr else p.stdout.decode(U8))
        return False
      f,n = [],[]
      for s in p.stdout.decode(U8).splitlines():
        for (k,x) in self.filter.items():
          c = x.get('targetcommand',None)
          if c and re.search(r'%s'%(re.sub('\'','\\\'',c)),cmd) is not None:
            i,d = x.get('filtertoinfo',None),x.get('filtertodebug',None)
            if (i and re.search(r'%s'%(re.sub('\'','\\\'',i)),s) is not None or
                d and re.search(r'%s'%(re.sub('\'','\\\'',d)),s) is not None):
              f.append((k,s))
              break
        else:
          n.append(s)
      for (k,x) in f:
        if self.filter[k].get('filtertoinfo',None):
          log.debug(f'[{k}]の設定({CONF})によりpcsのメッセージをフィルタリングします')
          info(x,self.filter[k].get('filterreason',None))
        else:
          debug(x,self.filter[k].get('filterreason',None))
      x = '\n'.join(n)
      if re.match(r'warning: ',x,flags=re.I) is not None:
        warn(x)
      elif x:
        info(x)
      return True
    except Exception as e:
      log.innererr('CIBファイルの出力に失敗しました',e)
      return False

  '''
    ローカルcib.xmlの初期化
    [引数]
      なし
    [戻り値]
      not None : 初期化用のコマンド文字列(OK時)
          None : NG時
  '''
  def init_cib(self):
    def fmtmsg(s,cmd):
      return log.indent(f'$ {cmd}\n{s}')
    m = 'CIBファイルの出力に失敗しました'
    try:
      if [x for x in self.root.getElementsByTagName(Mode.NODE.value) if x.childNodes] or self.live:
        c = f'pcs cluster cib {self.outxml}'
        log.debug(f'[コマンド_実行] {c}')
        p = subprocess.run(shlex.split(c),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if p.returncode != 0:
          log.error(f'{m}。クラスタを起動した状態で実行してください')
          log.error_r(fmtmsg(p.stderr.decode(U8) if p.stderr else p.stdout.decode(U8),c))
          return
        return f'{c}\n'
      else:
        c = 'cibadmin --empty'
        log.debug(f'[コマンド_実行] {c}')
        p = subprocess.run(shlex.split(c),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if p.returncode != 0:
          log.error(f'{m}')
          log.error_r(fmtmsg(p.stderr.decode(U8) if p.stderr else p.stdout.decode(U8),c))
          return
        with open(self.outxml,"w",encoding=U8) as f:
          f.write(p.stdout.decode(U8))
        return f'{c} > {self.outxml}\n'
    except Exception as e:
      log.innererr(f'{m}',e)

  '''
    XMLからpcsコマンド文字列を生成
    [引数]
      なし
    [戻り値]
      not None : pcsコマンド群文字列(OK時)
          None : NG時
  '''
  def xml2pcs(self):
    cib = self.init_cib()
    if not cib:
      return
    s = [
      cib,
      self.x2p_node(),
      self.x2p_option(Mode.PROP.value),
      self.x2p_option(Mode.RDEF.value),
      self.x2p_option(Mode.ODEF.value),
      self.x2p_resources(),
      self.x2p_stonith_lv(),
      self.x2p_location(),
      self.x2p_colocation(),
      self.x2p_order(),
      self.x2p_alert(),
      self.x2p_config()
    ]
    while [x for x in s if not x]:
      s.remove(None)
    return '\n'.join(s)

  def x2p_node(self):
    #
    # pcs node attribute(<type>)   <uname> <name>=<value>
    # pcs node utilization(<type>) <uname> <name>=<value>
    #
    s = []
    for x in self.root.getElementsByTagName(Mode.NODE.value):
      for y in [y for z in NODE_ATTR_TYPE for y in x.childNodes if z == y.nodeName]:
        for z in y.childNodes:
          s.append('%s %s %s %s=%s'%(
            PCSF[Mode.NODE.value], y.nodeName, x.getAttribute('uname'),
            z.getAttribute('name'), z.getAttribute('value') ))
          self.run_pcs(s[-1],z.getAttribute(ATTR_C))
    if s:
      return '%s\n%s\n'%(CMNT[Mode.NODE.value],'\n'.join(s))

  def x2p_option(self,tag):
    #
    # pcs property set <name>=<value>
    # pcs resource defaults update <name>=<value>
    # pcs resource op defaults update <name>=<value>
    #
    s = []
    for x in [x for y in self.root.getElementsByTagName(tag) for x in y.childNodes]:
      s.append('%s %s=%s'%(PCSF[tag],x.getAttribute('name'),x.getAttribute('value')))
      self.run_pcs(s[-1],x.getAttribute(ATTR_C))
    if s:
      return '%s\n%s\n'%(CMNT[tag],'\n'.join(s))

  def x2p_resources(self):
    if not self.rr:
      return
    s,pcd = [],{}
    for x in self.xml_get_childs(self.rr,[Mode.GRUP.value,Mode.CLNE.value,Mode.PROM.value]):
      for y in [y for y in x.childNodes if y.nodeName == 'rsc']:
        pcd[x.getAttribute('id')] = y.getAttribute('id')
    for x in [x for y in [Mode.PRIM.value,Mode.STNT.value]
      for x in self.rr.getElementsByTagName(y)]:
      s.append(self.x2p_rsc_primitive(x))
      for k1 in [k1 for (k1,v) in pcd.items() if v == x.getAttribute('id')]:
        s.append(self.x2p_rsc_advanced(self.xml_get_rscnode(k1)))
        for k2 in [k2 for (k2,v) in pcd.items() if v == k1]:
          s.append(self.x2p_rsc_advanced(self.xml_get_rscnode(k2)))
    if s:
      return '\n'.join(s)

  def x2p_rsc_primitive(self,node):
    def x2p_util(node):
      #
      # pcs resource utilization <resource id> <name>=<value>
      #
      s = []
      for x in [x for y in node.getElementsByTagName('utilization') for x in y.childNodes]:
        s.append('%s %s %s=%s'%(
          PCSF[Mode.RUTI.value], node.getAttribute('id'),
          x.getAttribute('name'), x.getAttribute('value') ))
        self.run_pcs(s[-1],x.getAttribute(ATTR_C))
      if s:
        s.insert(0,'')
        s.append('')
      return s
    #
    # pcs resource create <id> <class>:<provider>:<type>
    #   <resource options>
    #   meta <meta options>
    #   op <O:type> <operation options>
    #   [<O:type> <operation options>]
    #
    # pcs stonith create <id> <type>
    #   <stonith options>
    #   meta <meta options>
    #   op <O:type> <operation options>
    #   [<O:type> <operation options>]
    #
    s,z = [],[]
    if node.hasAttribute('class'):
      z.append(node.getAttribute('class'))
    if node.hasAttribute('provider'):
      z.append(node.getAttribute('provider'))
    z.append(node.getAttribute('type'))
    s.append('%s %s %s'%(PCSF[node.nodeName],node.getAttribute('id'),':'.join(z)))
    lno = node.getAttribute(ATTR_U)
    for (tag,opt) in [('options',None),('meta','meta')]:
      z = []
      for x in [x for y in node.getElementsByTagName(tag) for x in y.childNodes]:
        if not z and opt:
          z.append(f'{opt}')
        z.append(f"{x.getAttribute('name')}=\"{x.getAttribute('value')}\"")
      if z:
        s.append(' '.join(z))
    z = []
    for x in [x for y in node.getElementsByTagName('op') for x in y.childNodes]:
      nv = []
      for y in x.childNodes:
        nv.append(f"{y.getAttribute('name')}={y.getAttribute('value')}")
      if nv:
        z.append('%s %s'%(x.nodeName,' '.join(nv)))
    for (i,x) in enumerate(z):
      if i == 0:
        s.append(f'op {x}')
      else:
        s.append(x)
    self.run_pcs(' '.join(s),lno)
    return '%s\n%s\n%s'%(
      CMNT[node.nodeName], (' \\\n%s'%(''.rjust(4))).join(s), '\n'.join(x2p_util(node)) )

  def x2p_rsc_advanced(self,node):
    #
    # pcs resource group add <group id> <resource id>...
    # pcs resource clone <resource id | group id> <clone id>
    # pcs resource promotable <resource id | group id> <clone id>
    #  +
    # pcs resource meta <group id | clone id> <name>=<value>
    #
    s,z = [],[]
    if node.nodeName == Mode.GRUP.value:
      z.append(node.getAttribute('id'))
    for x in [x for x in node.childNodes if x.nodeName == 'rsc']:
      z.append(x.getAttribute('id'))
    if node.nodeName == Mode.CLNE.value or node.nodeName == Mode.PROM.value:
      z.append(node.getAttribute('id'))
    s.append(CMNT[node.nodeName])
    s.append('%s %s'%(PCSF[node.nodeName],' '.join(z)))
    self.run_pcs(s[-1],node.getAttribute(ATTR_C))
    z = []
    for x in [x for y in node.getElementsByTagName('meta') for x in y.childNodes]:
      z.append(f"{x.getAttribute('name')}={x.getAttribute('value')}")
    if z:
      s.append('%s %s %s'%(PCSF[Mode.RMET.value],node.getAttribute('id'),' '.join(z)))
      self.run_pcs(s[-1],node.getAttribute(ATTR_C))
    if s:
      return '%s\n'%('\n'.join(s))

  def x2p_stonith_lv(self):
    #
    # pcs stonith level add <level> <node> <id> --force
    #
    lv,s = [],[]
    for x in self.root.getElementsByTagName(Mode.STLV.value):
      lv.append((x.getAttribute('level'),x.getAttribute('node'),
        x.getAttribute('id'),x.getAttribute(ATTR_C)))
    if not lv:
      return
    lv.sort(key=lambda x:x[0])  #      sort by 'level' first,
    lv.sort(key=lambda x:x[1])  # then sort by 'node'
    for x in lv:
      #
      # 'pcs stonith level add ...'では"--force"オプションを指定しないとError
      # -> "--force"オプションを付与
      #
      # $ pcs --version
      # 0.10.1
      # $ pcs stonith level add 1 pm01 fence1-kdump
      # Error: Stonith resource(s) 'fence1-kdump' do not exist, use --force to override
      #
      s.append('%s %s --force'%(PCSF[Mode.STLV.value],' '.join(x[:3])))
      self.run_pcs(s[-1],x[3])
    if s:
      return '%s\n%s\n'%(CMNT[Mode.STLV.value],'\n'.join(s))

  def x2p_location(self):
    #
    # pcs constraint location <rsc> prefers <node>[=<score>]
    # pcs constraint location <rsc> avoids  <node>[=<score>]
    #
    # pcs constraint location <rsc> rule [role=master|slave] score=<score> <expression>
    #
    s = []
    for (l,x) in [(l,x) for l in self.root.getElementsByTagName(Mode.LOCN.value)
      for x in l.childNodes]:
      for y in x.childNodes:
        z = []
        z.append(f" {y.getAttribute('node')}")
        if y.getAttribute('score'):
          z.append(f"={y.getAttribute('score')}")
        s.append('%s %s %s%s'%(
          PCSF[Mode.LOCN.value], l.getAttribute('rsc'), x.nodeName, ''.join(z) ))
        self.run_pcs(s[-1],x.getAttribute(ATTR_C))
    for (l,x) in [(l,x) for l in self.root.getElementsByTagName(Mode.LOCR.value)
      for x in l.childNodes]:
      role = []
      if x.getAttribute('role'):
        role.append(f" role={x.getAttribute('role')}")
      exp = []
      for y in x.childNodes:
        z = []
        if y.getAttribute('op').lower() in LOC_RULE_UNARY:
          z.append(y.getAttribute('op'))
          z.append(y.getAttribute('attribute').replace('#','\#'))
        else:
          z.append(y.getAttribute('attribute').replace('#','\#'))
          z.append(y.getAttribute('op'))
          z.append(y.getAttribute('value'))
        exp.append(' '.join(z))
      z = f" {x.getAttribute('bool_op')} ".join(exp) if x.getAttribute('bool_op') else exp[0]
      s.append('%s %s rule%s score=%s %s'%(
        PCSF[Mode.LOCR.value], l.getAttribute('rsc'), ''.join(role), x.getAttribute('score'), z ))
      self.run_pcs(s[-1],x.getAttribute(ATTR_C))
    if s:
      return '%s\n%s\n'%(CMNT[Mode.LOCR.value],'\n'.join(s))

  def x2p_colocation(self):
    #
    # pcs constraint colocation add
    #  [<rsc-role>] <rsc> with [<with-rsc-role>] <with-rsc> score=<score>
    #
    s = []
    for x in self.root.getElementsByTagName(Mode.COLO.value):
      rr,wr = [],[]
      if x.getAttribute('rsc-role'):
        rr.append(f"{x.getAttribute('rsc-role')} ")
      if x.getAttribute('with-rsc-role'):
        wr.append(f"{x.getAttribute('with-rsc-role')} ")
      s.append('%s %s%s with %s%s score=%s'%(
        PCSF[Mode.COLO.value], ''.join(rr), x.getAttribute('rsc'),
        ''.join(wr), x.getAttribute('with-rsc'), x.getAttribute('score') ))
      self.run_pcs(s[-1],x.getAttribute(ATTR_C))
    if s:
      return '%s\n%s\n'%(CMNT[Mode.COLO.value],'\n'.join(s))

  def x2p_order(self):
    #
    # pcs constraint order
    #  [<first-action>] <first-rsc> then [<then-action>] <then-rsc>
    #  [kind=<kind>] [symmetrical=<symmetrical>
    #
    s = []
    for x in self.root.getElementsByTagName(Mode.ORDR.value):
      f,t,o = [],[],[]
      if x.getAttribute('first-action'):
        f.append(f"{x.getAttribute('first-action')} ")
      if x.getAttribute('then-action'):
        t.append(f"{x.getAttribute('then-action')} ")
      if x.getAttribute('kind'):
        o.append(f"kind={x.getAttribute('kind')}")
      if x.getAttribute('symmetrical'):
        o.append(f"symmetrical={x.getAttribute('symmetrical')}")
      s.append('%s %s%s then %s%s %s'%(
        PCSF[Mode.ORDR.value], ''.join(f), x.getAttribute('first-rsc'),
        ''.join(t), x.getAttribute('then-rsc'), ' '.join(o) ))
      self.run_pcs(s[-1],x.getAttribute(ATTR_C))
    if s:
      return '%s\n%s\n'%(CMNT[Mode.ORDR.value],'\n'.join(s))

  def x2p_alert(self):
    def x2p_attr(node,cmd):
      for x in ALRT_ATTR_TYPE:
        s = []
        for y in [y for z in self.xml_get_childs(node,[x]) for y in z.childNodes]:
          s.append(f"{y.getAttribute('name')}=\"{y.getAttribute('value')}\"")
        if s:
          cmd.append('%s %s'%(x,' '.join(s)))
    #
    # pcs alert create path=<path> id=<alert-id>
    #   options <option>=<value>...
    #   meta    <meta-option>=<value>...
    #
    # pcs alert recipient add <alert-id> value=<recipient-value>
    #   options <option>=<value>...
    #   meta    <meta-option>=<value>...
    #
    s = []
    for (i,x) in enumerate(self.root.getElementsByTagName(Mode.ALRT.value)):
      id = f'alert_{i+1}'; c = []
      c.append('%s path="%s" id=%s'%(PCSF[Mode.ALRT.value],x.getAttribute('path'),id))
      x2p_attr(x,c)
      if s:
        s.append('\n')
      s.append('%s\n%s\n'%(CMNT[Mode.ALRT.value],' \\\n  '.join(c)))
      self.run_pcs(' '.join(c),x.getAttribute(ATTR_C))
      for y in x.getElementsByTagName(Mode.AREC.value):
        c = []
        c.append('%s %s value=%s'%(PCSF[Mode.AREC.value],id,y.getAttribute('value')))
        x2p_attr(y,c)
        s.append('%s\n'%(' \\\n  '.join(c)))
        self.run_pcs(' '.join(c),y.getAttribute(ATTR_C))
    if s:
      return ''.join(s)

  def x2p_config(self):
    s = []
    for x in self.root.getElementsByTagName(Mode.CNFG.value):
      raw = x.getAttribute('data')
      if re.match(r'pcs -f ',raw) is None:
        raw = re.sub(r'^pcs ',f'{self.pcsf} ',raw)
      s.append(raw.replace('\n',' \\\n'))
      while raw.count('\n\n'):
        raw = raw.replace('\n\n','\n')
      c = raw.split('\n')
      for (i,y) in enumerate(c):
        c[i] = del_blank(y)
      self.run_pcs(' '.join(c),x.getAttribute(ATTR_C))
    if s:
      return '%s\n%s\n'%(CMNT[Mode.CNFG.value],'\n'.join(s))

  '''
    文字列をPCSファイルに書き出す
    [引数]
      s     : 文字列
    [戻り値]
      True  : OK
      False : NG
  '''
  def write_pcs(self,s):
    try:
      with open(self.outsh,'w',encoding=U8) as f:
        f.write(s)
        return True
    except Exception as e:
      log.innererr('PCSファイルの出力に失敗しました',e)
      return False

  def debug_input(self,clmd,RIl,csvl):
    if log.lv >= Log.DEBUG1:
      s = [f'[{self.mode[0]}:{self.mode[1]}]']
      for x in RIl:
        s.append(f'({x+1})RI[{csvl[x]}]')
      for (k,x) in dict2list(clmd):
        s.append(f'({x+1}){k}[{csvl[x]}]')
      log.debug1_l(' '.join(s))

  def xml_debug(self):
    if log.lv >= Log.DEBUG1:
      log.debug1('XML (CSVデータから生成) を出力します')
      log.stderr(self.root.toprettyxml(indent=' '))

  def msg_inval_fmt(self,tbl):
    return f'{tbl}の定義が正しくありません'
  def msg_dup_set(self,where,what,lno):
    return f'{where}の{what}は、既に{lno}行目で設定されています'
  def msg_no_data(self,clm):
    return f"'{clm}'列に値が設定されていません"
  def msg_inval_data(self,clm,val,opts):
    return f"'{clm}'列の「{val}」は無効な値です。有効な値は [{'/'.join(opts)}] です"
  def msg_disca_data(self,where):
    return f'{where}に値が設定されています'

class Log:
  LOGLV = {
    'ERROR':  0,
    'WARN':   1,
    'NOTICE': 2,
    'INFO':   3,
    'DEBUG':  4,
    'DEBUG1': 5
  }
  ERROR  = LOGLV['ERROR']
  WARN   = LOGLV['WARN']
  NOTICE = LOGLV['NOTICE']
  INFO   = LOGLV['INFO']
  DEBUG  = LOGLV['DEBUG']
  DEBUG1 = LOGLV['DEBUG1']

  lv_maxlen = 0
  for x in LOGLV:
    if len(x) > lv_maxlen:
      lv_maxlen = len(x)
  msginfo = ('CSV',None,None)
  indents = (0,'')
  last_w = ''

  def __init__(self):
    self.lv = self.ERROR
    self.lno = 0

  def error(self,msg):
    self.print2e(self.ERROR,msg)
  def error_l(self,msg):
    self.print2e(self.ERROR,msg,True)
  def error_r(self,msg):
    if self.ERROR > self.lv:
      return
    self.stderr(msg)

  def warn(self,msg):
    self.print2e(self.WARN,msg)
  def warn_l(self,msg):
    self.print2e(self.WARN,msg,True)
  def warn_r(self,msg):
    if self.WARN > self.lv:
      return
    self.stderr(msg)

  def notice(self,msg):
    self.print2e(self.NOTICE,msg)
  def notice_l(self,msg):
    self.print2e(self.NOTICE,msg,True)
  def notice_r(self,msg):
    if self.NOTICE > self.lv:
      return
    self.stderr(msg)

  def info(self,msg):
    self.print2e(self.INFO,msg)
  def info_l(self,msg):
    self.print2e(self.INFO,msg,True)
  def info_r(self,msg):
    if self.INFO > self.lv:
      return
    self.stderr(msg)

  def debug(self,msg):
    self.print2e(self.DEBUG,msg)
  def debug_l(self,msg):
    self.print2e(self.DEBUG,msg,True)
  def debug_r(self,msg):
    if self.DEBUG > self.lv:
      return
    self.stderr(msg)

  def debug1(self,msg):
    self.print2e(self.DEBUG1,msg)
  def debug1_l(self,msg):
    self.print2e(self.DEBUG1,msg,True)

  def innererr(self,msg,e):
    self.error(f'{msg} [内部エラー]')
    self.error_r(self.indent(str(e)))

  def fmterr_l(self,msg,lno=None):
    if lno:
      self.lno = lno
    self.error_l(f'{msg}')

  def indent(self,s):
    return re.sub(r'^|(\n)',r'\1' + f'{self.indents[1]}',s.rstrip('\n')) + '\n'

  def set_msginfo(self,outxml,outsh):
    self.msginfo = ('CSV',outxml,outsh)

  def exit(self,rc):
    pre = ''
    if self.last_w not in ('\n',''):
      pre = '\n'
    if rc == RC.SUCCESS or rc == RC.WARN:
      self.stderr(f'{pre}{self.msginfo[1]} (CIB), {self.msginfo[2]} (PCS) を出力しました。\n')
      return rc
    self.stderr(f'{pre}%s, %s を出力中にエラーが発生しました。%s\n'%(
                self.msginfo[1] if self.msginfo[1] else 'CIB',
                self.msginfo[2] if self.msginfo[2] else 'PCS',
                '処理を中止します。' if rc == RC.ERROR else ''))
    return RC.ERROR

  def print2e(self,lv,msg,print_lno=False):
    if lv == self.ERROR:
      global errflg; errflg = True
      global skipflg; skipflg = True
    elif lv == self.WARN:
      global warnflg; warnflg = True
    if lv > self.lv:
      return
    for k in [k for (k,x) in list(self.LOGLV.items()) if x == lv]:
      f = f"{k}{''.rjust(self.lv_maxlen - len(k))}: "
      self.indents = (len(f),''.rjust(len(f)))
    if print_lno:
      self.stderr(f'{f}({self.msginfo[0]}:L{str(self.lno).ljust(3)}) {msg}\n')
    else:
      self.stderr(f'{f}{msg}\n')

  def stderr(self,msg):
    sys.stderr.write(msg)
    sys.stderr.flush()
    self.last_w = msg

'''
  リスト(要素)のデータを整形する
    ・要素の前後の 全半角空白|タブ|改行 を削除(*)
    ・文字列中の改行を半角空白に置換(*)
  [引数]
    l      : 変換対象のリスト
    do_fmt : *の処理を行うか
  [戻り値]
    なし
'''
def fmt_item(l,do_fmt):
  for (i,x) in [(i,x) for (i,x) in enumerate(l) if x]:
    if do_fmt:
      while x.count('\n\n'):
        x = x.replace('\n\n','\n')
    l[i] = del_blank(x.replace('\n',' ')) if do_fmt else x

'''
  文字列の前後空白(全半角空白|タブ文字)を取り除く
  [引数]
    s : 文字列
  [戻り値]
    処理後の文字列
'''
def del_blank(s):
  z = s.strip().strip('　')
  if s == z:
    return z
  return del_blank(z)

'''
  文字列の後空白(全半角空白|タブ文字)を取り除く
  [引数]
    s : 文字列
  [戻り値]
    処理後の文字列
'''
def del_rblank(s):
  z = s.rstrip().rstrip('　')
  if s == z:
    return z
  return del_rblank(z)

'''
  辞書(dict)データをリストに変換
  [引数]
    d      : 辞書
    v_only : True  : リストの要素を (値)      にする
             False : リストの要素を (キー,値) にする
  [戻り値]
    辞書データのリスト
'''
def dict2list(d,v_only=None):
  l = list(d.values())
  l.sort()
  return l if v_only else [(k,x) for y in l for (k,x) in list(d.items()) if y == x]

'''
  列番号をExcelでの列名に変換
  [引数]
    pos : 列番号(0～255)
  [戻り値]
    列名('列A'～'列IV')
'''
def pos2clm(pos):
  s = ''
  pos = int(pos) + 1
  while pos:
    s = chr((pos - 1) % 26 + 65) + s
    pos = (pos - 1) // 26
  return f'列{s}'

def exit(rc):
  sys.exit(log.exit(rc))

try:
  sys.stdout = codecs.getwriter(U8)(sys.stdout.detach())
  sys.stderr = codecs.getwriter(U8)(sys.stderr.detach())
except Exception:
  sys.stderr.write('failed to encode stdout and stderr.\n')
  sys.exit(RC.ERROR)

if __name__ == '__main__':
  log = Log()
  gen = Gen()
  exit(gen.main())
