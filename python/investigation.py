import os
import json
from pandas import DataFrame, Series
import pandas as pd
import numpy as np
from nltk.metrics import *
import re
from string import Template
from math import floor
from operator import truediv
import codecs

folder_data_intermediate = '../data/intermediate'

if not os.path.exists(folder_data_intermediate):
    os.makedirs(folder_data_intermediate)


# ===============================
# STEP 1: Load input data in JSon format:

inputPath = '../data/input/'
listingData = [json.loads(line) for line in open(inputPath + 'listings.txt')]
productData = [json.loads(line) for line in open(inputPath + 'products.txt')]

# Convert input data into Pandas data frames:

listings = DataFrame(listingData).reset_index()
listings.rename(columns={'index': 'original_listing_index'}, inplace=True)
products = DataFrame(productData)

# ======================================================================
# STEP 2: Level 1 filtering: BY MANUFACTURER

# 2.1 Get lists of unique manufacturers in the 2 files (for matching them up):
lManufs = np.sort(listings['manufacturer']).unique()
pManufs = np.sort(products['manufacturer']).unique()
    # Note: inspecting the above will give encoding errors if using an older versions of Pandas. Ensure you have version 0.11 or more recent.

lManufsSeries = Series(lManufs)
pManufsSeries = Series(pManufs)

# pManufsSeries:
# 0               Agfa
# 1              Canon
# 2              Casio
# 3             Contax
# 4              Epson
# 5           Fujifilm
# 6                 HP
# 7              Kodak
# 8     Konica Minolta
# 9            Kyocera
# 10             Leica
# 11             Nikon
# 12           Olympus
# 13         Panasonic
# 14            Pentax
# 15             Ricoh
# 16           Samsung
# 17             Sanyo
# 18             Sigma
# 19              Sony
# 20           Toshiba


# ----------------------------------------------------------------------
# Data discoveries:
#   1. lManufs has far more manufacturers than pManufs, including some bad data which is clearly a product not a manufacturer
#   2. Some aren't even camera products (e.g. UBISOFT Assassin's Creed). 
#   3. Others are, but aren't on the main list of products e.g. listings[listings['manufacturer'] == u'Roots']
#   4. In some cases, the listing manufacturer is a subsidiary of the product manufacturer e.g. 'Canon Canada' under 'Canon'
#   5. At least one typo: 'Canoon' instead of 'Canon': listings[listings['manufacturer'] == u'Canoon']
#   6. Product manufacturer gotchas to avoid:
#      6.1 Konica Minolta is two words, but it's simpler to match on single words rather than bigrams. 
#          So match on each word, not the combination. This will also catch cases where either word is used alone.
#      6.2 HP could also match Hewlett Packard. But that's two words. So match on "HP" or "Hewlett" or "Packard".
#      6.3 Fujifilm could also match Fuji or "Fuji film". So rather just match on "Fuji" not "Fujifilm"

# ----------------------------------------------------------------------
# 2.2 Generate and clean up manufacturer mappings in products data:
pManufsMapping = DataFrame( 
    { 'pManuf': pManufsSeries, 'Keyword': pManufsSeries.str.lower() } 
) # By default map each word to itself
pManufsMapping['Keyword'][pManufsMapping['pManuf'] == 'Konica Minolta'] = 'konica'
pManufsMapping = pManufsMapping.append( { 'pManuf': 'Konica Minolta', 'Keyword': 'minolta' }, ignore_index = True )
pManufsMapping = pManufsMapping.append( { 'pManuf': 'HP', 'Keyword': 'hewlett' }, ignore_index = True )
pManufsMapping = pManufsMapping.append( { 'pManuf': 'HP', 'Keyword': 'packard' }, ignore_index = True )
pManufsMapping['Keyword'][pManufsMapping['pManuf'] == 'Fujifilm'] = 'fuji'

pManufKeywords = pManufsMapping['Keyword']

# ----------------------------------------------------------------------
# 2.3 Experiment with Levenshtein distances between various similar strings:
s1 = 'Canon'
s2 = 'Canoon'
s3 = 'Cannon'
s4 = 'Cannoon'
s5 = 'Cannonn'
s_nikon = 'Nikon'

# Decide on a reasonable Levenshtein distance for matching manufacturer names:
edit_distance(s1, s2) # 1
edit_distance(s1, s3) # 1
edit_distance(s1, s4) # 2
edit_distance(s1, s5) # 2
edit_distance(s1, s_nikon) # 3

# test...
# min_manuf_word_len = 3
#test...
# edit_distance_threshold = 1

# Safest parameters:
edit_distance_threshold = 2
min_manuf_word_len = 4

# ----------------------------------------------------------------------
# 2.4 Match lManufs to pManufs:
# 
# Precedence:
# 1. Exact match on entire string
# 2. Exact match on a single word in the string
# 3. Match contained in a single word in the string
# 4. Sufficiently small Levenshtein distance to a single word in the string
def matchManuf(lManuf):
    splits = lManuf.lower().split()
    for pManufKeyword in pManufKeywords:
        if pManufKeyword in splits:
            return pManufKeyword
    foundPManufs = [ p for s in splits
                       for p in pManufKeywords
                       if s.find(p.lower()) >= 0
                   ]
    if len(foundPManufs) > 0:
        return foundPManufs[0]
    levenshteinPManufs = [ p for s in splits
                             for p in pManufKeywords
                             if len(s) > min_manuf_word_len 
                             and edit_distance(s, p.lower()) <= edit_distance_threshold
                         ]
    if len(levenshteinPManufs) > 0:
        return levenshteinPManufs[0]
    return ''

mapData = { 'lManuf': lManufsSeries,
            'pManufKeyword': lManufsSeries.apply( matchManuf )
          }
lManufMap = DataFrame( mapData )
lManufMap = pd.merge( lManufMap, pManufsMapping, how='left', left_on='pManufKeyword', right_on='Keyword')
del lManufMap['Keyword']
lManufMap['pManuf'] = lManufMap['pManuf'].fillna('')
lManufMap

# ----------------------------------------------------------------------
# 2.5 Output intermediate data to check the accuracy of the manufacturer matching:
# 
#Possible mismatches:
def isPossibleMismatch(row):
    return row['pManuf'] != '' and (row['lManuf'].lower().find(row['pManuf'].lower()) == -1)

possibleMismatches = lManufMap.apply(isPossibleMismatch, axis=1)
# This trick was found at: 
#   http://stackoverflow.com/questions/13331698/how-to-apply-a-function-to-two-columns-of-pandas-dataframe
# An alternate approach would have been to modify matchManuf to also return the type of match, as described here: 
#   http://stackoverflow.com/questions/12356501/pandas-create-two-new-columns-in-a-dataframe-with-values-calculated-from-a-pre?rq=1

lManufMap[lManufMap['pManuf'] == ''].to_csv('../data/intermediate/unmatched_manufs.csv', encoding='utf-8')
lManufMap[lManufMap['pManuf'] != ''].to_csv('../data/intermediate/matched_manufs.csv', encoding='utf-8')
lManufMap[possibleMismatches].to_csv('../data/intermediate/possible_mismatched_manufs.csv', encoding='utf-8')
# ASSUMPTION: using utf-8 encodings will be sufficient. 
# Note that Excel may show some less common letters as a "?". But in a text editor they are correct.

lManufMap[possibleMismatches]

#                           lManuf pManufKeyword          pManuf
# 428                   CANAL TOYS         canon           Canon
# 435                       Canoon         canon           Canon
# 439       Midland Consumer Radio         casio           Casio
# 440        Clip Sonic Technology        konica  Konica Minolta
# 441                       Konica        konica  Konica Minolta
# 447                      Epsilon         epson           Epson
# 451                         Fuji          fuji        Fujifilm
# 452                Fuji Film USA          fuji        Fujifilm
# 453                 Fuji FinePix          fuji        Fujifilm
# 454  Fuji Photo Film Europe GmbH          fuji        Fujifilm
# 455    Fuji Photo Film Usa, Inc.          fuji        Fujifilm
# 460              Hewlett Packard       hewlett              HP
# 461         Hewlett Packard GmbH       hewlett              HP
# 464                        LESCA         leica           Leica
# 466                        Leitz         leica           Leica
# 467                        Lenco         leica           Leica
# 469                      Minolta       minolta  Konica Minolta
# 475                      OPYMPUS       olympus         Olympus
# 476                      Olmypus       olympus         Olympus
# 482                     Olymypus       olympus         Olympus
# 498                      SAMYANG       samsung         Samsung
# 521           Syntax Corporation        contax          Contax

# DECISION: Quite a few of the above are mismatches. 
#           However the various olympus mappings and (possibly) canoon are correctly matched.
#           So rather allow all of these through and let the next layer of matching eliminate them.
#           
#           The alternative is to hard-code their elimination.
#           But rather avoid unnecessary customizations.

# DISCOVERIES:
# 1. Inspecting the 3 csv files showed up some anomalies.
#    This led to the new step 2.2 and subsequent refactorings.

# ----------------------------------------------------------------------
# 2.6 Map to manufacturers
# 

listingsByPManufAll = pd.merge( listings, lManufMap, how='inner', left_on='manufacturer', right_on='lManuf')
listingsByPManuf = listingsByPManufAll[listingsByPManufAll['pManuf'] != ''].reindex(columns = ['pManuf','lManuf', 'title','currency','price', 'original_listing_index'])
listingsByPManuf.to_csv('../data/intermediate/filtered_listings_by_pmanuf.csv', encoding='utf-8')


# ==============================================================================
# 3. Prepare the listings data for matching to products
# 

# ----------------------------------------------------------------------
# 3.1 Define terms that filter the product info from ancillary info
# 

# Languages found by inspecting csv files: English, French, German...
applicabilitySplitTerms = [ u'for', u'pour', u'f�r', u'fur', u'fuer' ]
additionalSplitTerms = [ 'with',  'w/', 'avec', 'mit', '+' ]

applicabilityPatterns = '|'.join([ re.escape(term) for term in applicabilitySplitTerms ])
additionalPatterns = '|'.join([ re.escape(term) for term in additionalSplitTerms ])
allTermPatterns = applicabilityPatterns + '|' + additionalPatterns

patternToExpand = ur'''
^
\s*
(?P<productDesc>
  (?:
    (?!
      (?<!\w)
      (?:$allTermPatterns)
      (?!\w)
    )
    .
  )+
  # Ensure the last character is non-whitespace:
  (?:
    (?!
      (?<!\w)
      (?:$allTermPatterns)
      (?!\w)
    )
    \S
  )
)
\s*
(?:
  (?P<extraProdDetailsSection>
    (?:
      (?:$allTermPatterns)
      \W*
    )
    (?P<extraProdDetails>
      .+
      \S # Ensure the last character is non-whitespace:
    )
  )
  \s*
)?
$$
'''

patternTemplate = Template(patternToExpand)
titleSplitRegexPattern = patternTemplate.substitute(allTermPatterns=allTermPatterns)
titleSplitRegex = re.compile( titleSplitRegexPattern, re.IGNORECASE | re.UNICODE | re.VERBOSE )

#testing regex matches...
regexTestString = '   Nikon EN-EL9a 1080mAh Ultra High Capacity Li-ion Battery Pack   for Nikon D40, D40x, D60, D3000, & D5000 Digital SLR Cameras with love  for ever   with   salt and pepper'
testMatch = titleSplitRegex.match(regexTestString)
if testMatch:
  testMatch.group('productDesc')
  testMatch.group('extraProdDetails')
  # Discovery: Python provides no way to access all the captures for a named capture group if there is more than one (e.g. the text "for" is repeated)
  # Action: Simplify the regex to have a named captured group for extraProdDetails, instead of multiple ones

  
# ----------------------------------------------------------------------
# 3.2 Split the product titles into a product description and ancillary information
# 

def splitTitle(title):
    titleMatch = titleSplitRegex.match(title)
    return titleMatch.group('productDesc'), titleMatch.group('extraProdDetails')

title_regex_pairs = listingsByPManuf['title'].apply(splitTitle)
productDescs, extraProdDetails = zip(* title_regex_pairs )
listingsByPManuf['productDesc'] = productDescs
listingsByPManuf['extraProdDetails'] = extraProdDetails

listingsByPManuf.to_csv('../data/intermediate/filtered_by_pmanuf_with_split_title.csv', encoding='utf-8')

# Check that the following give empty data frames:
# listingsByPManuf[pd.isnull(listingsByPManuf['productDesc'])]
# listingsByPManuf[listingsByPManuf['productDesc'] == '']

  
# ----------------------------------------------------------------------
# 3.3 Group by the product descriptions to reduce the amount of matching required
# 

productDescGrouping = listingsByPManuf.groupby(['pManuf', 'productDesc'])


# ==============================================================================
# 4. Prepare the products for matching to listings by finding duplicates:
# 

# ----------------------------------------------------------------------
# 4.1 Find duplicate models:
prod_model_counts = products.model.value_counts()
dup_models = prod_model_counts[prod_model_counts > 1]
#                     announced-date      family manufacturer   model
# 226  2011-02-15T19:00:00.000-05:00  Cybershot          Sony    T110
# 257  2009-02-16T19:00:00.000-05:00         NaN      Samsung   SL202
# 288  2011-02-15T19:00:00.000-05:00     FinePix     Fujifilm   S4000
# 370  2011-02-06T19:00:00.000-05:00        ELPH        Canon  300 HS
# 510  1998-11-01T19:00:00.000-05:00         NaN      Olympus   C900Z
# 517  1998-02-02T19:00:00.000-05:00     FinePix     Fujifilm     700
# 653  1999-04-15T20:00:00.000-04:00     PhotoPC        Epson     800
# 711  1998-03-15T19:00:00.000-05:00     Coolpix        Nikon     600
# 718  1999-02-14T19:00:00.000-05:00     Coolpix        Nikon     700
# 722  1996-05-12T20:00:00.000-04:00   PowerShot        Canon     600

# ------------------------------------------
# 4.2 Find duplicates by manufacturer and model:

products[products.duplicated(['manufacturer', 'model'])]
#                     announced-date family manufacturer   model
# 257  2009-02-16T19:00:00.000-05:00    NaN      Samsung   SL202
# 370  2011-02-06T19:00:00.000-05:00   ELPH        Canon  300 HS

# The problem with duplicated() is that it omits the first duplicate found.
# The following code allows us to examine the 'family' values for all records:
manuf_model_groups = products.groupby(['manufacturer', 'model'])
manuf_model_group_sizes = manuf_model_groups.size()
manuf_model_sizes = DataFrame({'group_count' : manuf_model_group_sizes}).reset_index()
manuf_model_dup_groups = manuf_model_sizes[manuf_model_sizes.group_count > 1]
manuf_model_dups = pd.merge(products, manuf_model_dup_groups, on=['manufacturer','model'], sort=True)[['manufacturer','family','model','announced-date']]
manuf_model_dups
#   manufacturer family   model                 announced-date
# 0        Canon   IXUS  300 HS  2010-05-10T20:00:00.000-04:00
# 1        Canon   ELPH  300 HS  2011-02-06T19:00:00.000-05:00
# 2      Samsung    NaN   SL202  2009-02-16T19:00:00.000-05:00
# 3      Samsung    NaN   SL202  2009-02-16T19:00:00.000-05:00


# ----------------------------------------------------------------------
# 4.3 Set the required matching action on the duplicates:
# 
# Note: A new text column named 'matchRule' will be added to the data frame.
#       Its value will guide the behaviour of the matching algorithm.
# 

# Ignore products which match on all 3 fields: manufacturer, family and model
manFamModel_dups = DataFrame({'isDup': products.duplicated(['manufacturer', 'family', 'model'])})
manFamModel_dups['matchRule'] = ''
manFamModel_dups.matchRule[manFamModel_dups.isDup] = 'ignore'

products['matchRule'] = manFamModel_dups.matchRule[manFamModel_dups.isDup]

# Match on family and model if the manufacturer and model are duplicated (but not the family):
manuf_model_groups = products[products.matchRule.isnull()].groupby(['manufacturer', 'model'])
manuf_model_group_sizes = manuf_model_groups.size()
manuf_model_sizes = DataFrame({'group_count' : manuf_model_group_sizes}).reset_index()  # reset_index() will copy the index into a column named 'index'
manuf_model_dup_groups = manuf_model_sizes[manuf_model_sizes.group_count > 1]

products2 = products.reset_index()  
    # products2 now has its index copied to a column named 'index'
    # This will be useful for matching up to the original index after the merge below...
manuf_model_dups = pd.merge(products2, manuf_model_dup_groups, on=['manufacturer','model'], sort=True).set_index('index')[['manufacturer','family','model']]
manuf_model_dups['matchRule'] = 'familyAndModel'
products = products.combine_first(manuf_model_dups[['matchRule']])  
    # Note: combine_first() is like a vectorized coalesce.
    #       It matches rows based on index.
    #       For each row and each column it takes the first non-null value
    #       in the two data frames (products and manuf_model_dups).

# test: products[products.matchRule.notnull()]


# ==============================================================================
# 5. Analyze the model column in the products data set in preparation 
#    for setting up rules for matching listings to products
# 

# ----------------------------------------------------------------------
# 5.1 Set up test regex for splitting the model into an array
#     of alphanumeric and non-alphanumeric sections
# 

regexTestString = ':::aaa-bb def   ghi   '

# Following regex pattern works to split with .Net, but not Python:
alphaNumSplitRegexPattern = r'(?<!^)\b'
alphaNumSplitRegex = re.compile( alphaNumSplitRegexPattern, re.IGNORECASE | re.UNICODE | re.VERBOSE )
alphaNumSplitRegex.split(regexTestString)

# This doesn't work either:
alphaNumSplitRegexPattern = '\b'
alphaNumSplitRegex = re.compile( alphaNumSplitRegexPattern, re.IGNORECASE | re.UNICODE | re.VERBOSE )
alphaNumSplitRegex.split(regexTestString)

# This also only works with .Net (\b seems to work differently)...
alphaNumRegexPattern = '(?:^|\b)(?:\w+|\W+)'
alphaNumRegex = re.compile( alphaNumRegexPattern, re.IGNORECASE | re.UNICODE | re.VERBOSE )
alphaNumRegex.findall(regexTestString)

# This works:
alphaNumRegexPattern = '\w+|\W+'
alphaNumRegex = re.compile( alphaNumRegexPattern, re.IGNORECASE | re.UNICODE | re.VERBOSE )
alphaNumRegex.findall(regexTestString)
alphaNumRegex.findall('aaa-bbb-ccc::ddd   ')
alphaNumRegex.findall('    aaa-bbb-ccc::ddd   ')

# Improve this to differentiate alphabetic blocks from numeric blocks as well
alphaNumRegexPattern = '[A-Za-z]+|\d+|\W+'
alphaNumRegex = re.compile( alphaNumRegexPattern, re.IGNORECASE | re.UNICODE | re.VERBOSE )
alphaNumRegex.findall(regexTestString)
alphaNumRegex.findall('aaa15-10bbb-ccc::ddd   ')
alphaNumRegex.findall('    aaa-bbb-ccc::dad   ')
alphaNumRegex.findall('DSC-V100 / X100')

def split_into_blocks_by_alpha_num(stringToSplit):
    return alphaNumRegex.findall(stringToSplit)


# ----------------------------------------------------------------------
# 5.2 Categorize each block into one of the following:
#     x = An 'x' on its own (so that an "x4" zoom specification is not seen as a product code)
#     c = consonants only
#     a = alphabetic only
#     n = numeric only
#     _ = white space (1 or more i.e. \s+)
#     - = a dash only, since this is likely to be a common character in product codes
#     ~ = a dash preceded or succeeded by whitespace characters
#     ( = a left bracket, possibly with whitespace on either side
#     ) = a right bracket, possibly with whitespace on either side
#     ! = a division symbol (/), possibly with whitespace on either side
#         Note: an exclamation mark is used since this character can be part of a file name
#     . = a single dot (no white space)
#     # = any other non-alphanumeric sequences
#
# SUBSEQUENTLY REMOVED: 
#     w = a combination of alphabetic and numeric characters
#

# Use a list of tuples (instead of a dictionary) to control order of checking (dictionaries are unordered):
blockClassifications = [
        ('x', r'^x$'), # An 'x' on its own. This is to avoid treating something like an "x4" zoom specification as a product code
        ('c', r'^[B-DF-HJ-NP-TV-XZb-df-hj-np-tv-xz]+$'),
        ('a', r'^[A-Za-z]+$'),
        ('n', r'^\d+$'),
        ('_', r'^\s+$'),
        ('-', r'^\-$'),
        ('~', r'^\s*\-\s*$'),  # Allow spaces on either side of the dash
        ('(', r'^\s*\(\s*$'),  # To cater for "GXR (A12)"
        (')', r'^\s*\)\s*$'),  # To cater for "GXR (A12)"
        ('!', r'^\s*\/\s*$'),  # To cater for "DSC-V100 / X100"
        ('.', r'^\.$'),        # To cater for "4.3"
        ('#', r'^.+$')         # An unknown character
    ]
    # A potential issue here is that the regex patterns assume ANSI characters.
    # However it seems that all the products listed are English, so this shouldn't matter.
    
blockClassificationRegexes = [(classifier, re.compile(pattern, re.IGNORECASE | re.UNICODE | re.VERBOSE )) for (classifier,pattern) in blockClassifications]

def derive_classification(blockToClassify):
    for (classifier, regex) in blockClassificationRegexes:
        if regex.match(blockToClassify):
            return classifier
    return '$'

# Test classification function
# 
# Note: These should be moved into a unit test class 
#       when converting this exploratory script into an application
# 
def test_classification(blockToClassify, expected):
    classification = derive_classification(blockToClassify)
    if classification != expected:
        print '"{0}" classified as "{1}". But "{2}" expected!'.format(blockToClassify, classification, expected)

#Expect following to fail (test that test_classification works properly):
# test_classification('abcd', 'test_failure to test the test method')

# Expect these to succeed:
test_classification('x', 'x')
test_classification('abcd', 'a')
test_classification('1234', 'n')
test_classification('bcd', 'c')
test_classification('d', 'c')
test_classification('D', 'c')
test_classification(' \t ', '_')
test_classification('-', '-')
test_classification('   -  ', '~')
test_classification(':', '#')
test_classification(':-)', '#')
test_classification('', '$')
test_classification('.', '.')
test_classification('/', '!')
test_classification('  /  ', '!')
test_classification('(', '(')
test_classification('  (  ', '(')
test_classification('  )  ', ')')

# ----------------------------------------------------------------------
# 5.3 Categorize a list of blocks into a 
#     single concatenated string of classifications:
#

def derive_classifications(blocksToClassify):
    block_classifications = [derive_classification(block) for block in blocksToClassify]
    classification = ''.join(block_classifications)
    
    # Convert an 'x' back to a consonant block 'c' if it is:
    #   a. not succeeded by an 'n', or
    #   b. preceded by a dash
    classification = re.sub(r'x(?!n)', 'c', classification)
    classification = re.sub(r'(?<=\-)x', 'c', classification)
    
    # There is no need to differentiate consonant blocks from other alphabetic blocks 
    # if a dash or number precedes or succeeds the consonant block 
    # (since that already indicates a product code pattern)...
    classification = re.sub(r'(?<=\-|n)c', 'a', classification)
    classification = re.sub(r'c(?=\-|n)', 'a', classification)
    return classification

def test_derive_classifications(blocksToClassify, expected):
    classification = derive_classifications(blocksToClassify)
    if classification != expected:
        print '"{0}" classified as "{1}". But "{2}" expected!'.format(','.join(blocksToClassify), classification, expected)

# test that test_derive_classifications works by giving an incorrect expectation:
# test_derive_classifications(['abc','12','-','abc',':','12', '  ','MP'], 'test_failure to test the test method')

# Expect these to succeed:
test_derive_classifications(['abc', '12','-','bc',':','12', '  ','MP'], 'an-a#n_c')
test_derive_classifications(['abc', ' ', 'bc','-','12',':','12', '  ','MP'], 'a_a-n#n_c')
test_derive_classifications(['  :  ','  -  ','12','.','1','MP', '','IS'], '#~n.na$a')
test_derive_classifications([],'')
test_derive_classifications(['jklmn'],'c')
test_derive_classifications(['jklmn',' '],'c_')
test_derive_classifications(['jklmn','15'],'an')
test_derive_classifications(['15', 'jklmn'],'na')
test_derive_classifications(['x','400'], 'xn')
test_derive_classifications(['x',' '], 'c_')
test_derive_classifications(['x'], 'c')
test_derive_classifications(['-','x','100'], '-an')
test_derive_classifications(['ax','400'], 'an')

# ----------------------------------------------------------------------
# 5.4 Convert a string into a list of tuples, where each tuple contains:
#     a. A list of the various alphanumeric and non-alphanumeric blocks
#     b. The classification string for the list of blocks
#

def get_blocks_and_classification_tuple(text_to_classify):
    blocks = split_into_blocks_by_alpha_num(text_to_classify)
    classification = derive_classifications(blocks)
    return blocks, classification

model_block_pairs = products['model'].apply(get_blocks_and_classification_tuple)
model_blocks, model_classifications = zip(* model_block_pairs )
products['model_blocks'] = model_blocks
products['model_classification'] = model_classifications

# See how many patterns there are:
# 
# Quick way...
# products.model_classification.value_counts()
# 
# Better way (can get examples too)...

def group_and_save_classification_patterns(source_column, classification_column, columns_to_export, classification_folder):
  classification_patterns = products.groupby(classification_column)
  classification_record_counts = products[classification_column].value_counts()
  #Ensure the folder path exists:   
  pattern_folder_path = r'../data/intermediate/' + classification_folder
  if not os.path.exists(pattern_folder_path):
      os.makedirs(pattern_folder_path)
  # Save a csv file per pattern, and write a summary record to the console:
  for pattern, group in classification_patterns:
      example = group.iloc[0][source_column]
      record_count = classification_record_counts[pattern]
      print 'Pattern: {0:<15} count: {1:<6} example: {2}'.format(pattern, record_count, example)
      # Write to an intermediate file for further investigation:
      pattern_file_path = r'{0}/{1}.csv'.format(pattern_folder_path, pattern)
      group[columns_to_export].to_csv(pattern_file_path, encoding='utf-8')
  print ''

group_and_save_classification_patterns('model', 'model_classification', ['manufacturer','family','model','model_classification','model_blocks'], 'model_classifications')

# Original classification patterns found in 'model' column BEFORE REFACTORING:
# 
# Pattern: a             count: 4     example: Digilux
# Pattern: a-a           count: 2     example: K-r
# Pattern: a-a_n         count: 2     example: V-LUX 20
# Pattern: a-n           count: 56    example: NEX-3
# Pattern: a-n_a         count: 20    example: C-2500 L
# Pattern: a-w           count: 198   example: DSC-W310
# Pattern: a-w_a_a       count: 1     example: EOS-1D Mark IV
# Pattern: a-wxw         count: 1     example: DSC-V100 / X100
# Pattern: a_a           count: 1     example: N Digital
# Pattern: a_a-w         count: 5     example: PEN E-P2
# Pattern: a_a_a         count: 1     example: GR Digital III
# Pattern: a_a_n         count: 7     example: mju Tough 8010
# Pattern: a_a_w         count: 1     example: Kiss Digital X3
# Pattern: a_n           count: 12    example: mju 9010
# Pattern: a_n_a         count: 2     example: EX 1500 Zoom
# Pattern: a_w           count: 4     example: Mini M200
# Pattern: axwx          count: 1     example: GXR (A12)
# Pattern: n             count: 36    example: 1500
# Pattern: n_a           count: 24    example: 130 IS
# Pattern: nxn           count: 1     example: 4.3
# Pattern: w             count: 329   example: TL240
# Pattern: w_a           count: 34    example: SD980 IS
# Pattern: w_ax          count: 1     example: CL30 Clik!
# 

# ----------------------------------------------------------------------
# Notes based on above matches:
# 
# 1. At this point there are only 4 patterns (with 1 record each) using the unmatched 'x' characters.
#    These could just be ignored. However there is a risk, because we don't know how how many matching *listings* there might be.
#    Alternatively, 3 of these can be handled by adding support for: /.()
#    Adding custom support for the '!' in "CL30 Clik!" doesn't seem worth it, and the CL30 product code might be good enough.
# 
# 2. There are 329 'w' patterns which are pieces of text with both alphabetic and numberic characters.
#    These are likely to all be product codes.. Consider the example: "TL240".
#    It would be better to match this on all of: "TL240", "TL-240", "TL 240".
#    So rather remove the 'w' block and always differentiate alphabetic from numeric.
# 
# 3. Consider the GXR. This consists only of consonants, indicating that it is also a product code.
#    So add a new match on words that are all consonants.
#    
#    But bear in mind the following:
#    
#    a. Consonant blocks that are preceded or succeeded by a dash or number, are clearly product codes because of the dash / number.
#       So 'normalize' classification codes by replacing 'c' codes with 'a' codes if preceded or succeeded by a dash or number.
#       This will reduce the total number of classification patterns to deal with.
#
#    b. They may not be product codes. They could also be domain-specific abbreviations or units of measure.
#       For example, "MP" for mega-pixels.
#       
#       Let's list all the consonant blocks first to see if this is really an issue.
#       If it is a problem, then only add a list of all consonant strings to convert to 'a' classifications.
#
# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# Classification patterns found in 'model' column after refactoring:
# 
# Pattern: a               count: 4      example: Digilux
# Pattern: a-a             count: 2      example: K-r
# Pattern: a-a_n           count: 2      example: V-LUX 20
# Pattern: a-an            count: 167    example: DSC-W310
# Pattern: a-an!an         count: 1      example: DSC-V100 / X100
# Pattern: a-ana           count: 10     example: DSC-HX100v
# Pattern: a-n             count: 56     example: NEX-3
# Pattern: a-n_a           count: 17     example: C-2000 Zoom
# Pattern: a-n_c           count: 3      example: C-2500 L
# Pattern: a-na            count: 21     example: QV-5000SX
# Pattern: a-na_a_a        count: 1      example: EOS-1D Mark IV
# Pattern: a_a-an          count: 4      example: PEN E-P2
# Pattern: a_a-ana         count: 1      example: PEN E-PL1s
# Pattern: a_a_an          count: 1      example: Kiss Digital X3
# Pattern: a_a_n           count: 7      example: mju Tough 8010
# Pattern: a_an            count: 3      example: Mini M200
# Pattern: a_n             count: 12     example: mju 9010
# Pattern: a_n_a           count: 2      example: EX 1500 Zoom
# Pattern: a_na            count: 1      example: mju 550WP
# Pattern: an              count: 277    example: TL240
# Pattern: an_a            count: 31     example: SD980 IS
# Pattern: an_ax           count: 1      example: CL30 Clik!
# Pattern: an_c            count: 3      example: SX220 HS
# Pattern: ana             count: 37     example: Z900EXR
# Pattern: c(an)           count: 1      example: GXR (A12)
# Pattern: c_a             count: 1      example: N Digital
# Pattern: c_a_a           count: 1      example: GR Digital III
# Pattern: n               count: 36     example: 1500
# Pattern: n.n             count: 1      example: 4.3
# Pattern: n_a             count: 16     example: 130 IS
# Pattern: n_c             count: 8      example: 310 HS
# Pattern: na              count: 15     example: 900S
#
# Note: 32 classification patterns after the refactoring, compared to 23 before. So not untractable.
#

# ----------------------------------------------------------------------
# Classification patterns found in 'model' column after a refactoring
# to treat a solitary 'x' as its own pattern, but only if succeeded by a number
# 
# This is to ensure that an "x4" is not erroneously treated as a product code, 
# since it could also be a zoom specification.
#
# Pattern: a               count: 4      example: Digilux
# Pattern: a-a             count: 2      example: K-r
# Pattern: a-a_n           count: 2      example: V-LUX 20
# Pattern: a-an            count: 167    example: DSC-W310
# Pattern: a-an!xn         count: 1      example: DSC-V100 / X100
# Pattern: a-ana           count: 10     example: DSC-HX100v
# Pattern: a-n             count: 56     example: NEX-3
# Pattern: a-n_a           count: 17     example: C-2000 Zoom
# Pattern: a-n_c           count: 3      example: C-2500 L
# Pattern: a-na            count: 21     example: QV-5000SX
# Pattern: a-na_a_a        count: 1      example: EOS-1D Mark IV
# Pattern: a_a-an          count: 4      example: PEN E-P2
# Pattern: a_a-ana         count: 1      example: PEN E-PL1s
# Pattern: a_a_n           count: 7      example: mju Tough 8010
# Pattern: a_a_xn          count: 1      example: Kiss Digital X3
# Pattern: a_an            count: 2      example: Mini M200
# Pattern: a_n             count: 12     example: mju 9010
# Pattern: a_n_a           count: 2      example: EX 1500 Zoom
# Pattern: a_na            count: 1      example: mju 550WP
# Pattern: a_xn            count: 1      example: Kiss X4
# Pattern: an              count: 273    example: TL240
# Pattern: an_a            count: 31     example: SD980 IS
# Pattern: an_a#           count: 1      example: CL30 Clik!
# Pattern: an_c            count: 2      example: SX220 HS
# Pattern: ana             count: 37     example: Z900EXR
# Pattern: c(an)           count: 1      example: GXR (A12)
# Pattern: c_a             count: 1      example: N Digital
# Pattern: c_a_a           count: 1      example: GR Digital III
# Pattern: n               count: 36     example: 1500
# Pattern: n.n             count: 1      example: 4.3
# Pattern: n_a             count: 16     example: 130 IS
# Pattern: n_c             count: 8      example: 310 HS
# Pattern: na              count: 15     example: 900S
# Pattern: xn              count: 4      example: X70
# Pattern: xn_c            count: 1      example: X560 WP


# ==============================================================================
# 6. Analyze the family column in the products data set
#    to decide how to combine it with the model search patterns:
# 

# ----------------------------------------------------------------------
# 6.1 See how much variability there is in the family column:
# 

products.family.fillna('').value_counts().sort_index()

#                 258
# Alpha            13
# Coolpix          43
# Cyber-shot       42
# Cybershot         8
# Cybershot         6
# D-LUX             1
# DiMAGE            4
# Digilux           2
# Digital IXUS      9
# ELPH              3
# EOS               8
# EasyShare        24
# Easyshare         2
# Exilim           30
# FinePix          85
# Finecam           1
# Finepix           1
# IXUS              5
# IXY               5
# Lumix            80
# Mavica           10
# Optio            16
# PhotoPC           9
# Photosmart        7
# PowerShot        46
# Rebel             4
# Stylus           14
# Tough             1
# ePhoto            6

# Notes based on above:
# 
# 1. Some duplication:
#       a. Cybershot, "Cybershot ", Cyber-shot
#            TIP: above diagnosed using... products[products.family.str.startswith('Cyber').fillna(False)]
#       b. Digital IXUS, IXUS
#       c. EasyShare, Easyshare
#       d. FinePix, Finepix
# 
# 2. Many records don't have a family. Of the remainder, all are pure alphabetic, except for:
#       a. A space to be trimmed from " Cybershot"
#       b. A dash in Cyber-shot and D-Lux
#       c. A space in "Digital IXUS"
# 
# Conclusions: 
# 
# 1. The data looks cleaner than expected.
#    Even the extra dash in Cyber-shot shouldn't matter, as 
#    the pattern matching regex will probably treat the dash as optional anyway.
# 
# 2. The classification patterns will be fairly uniform.
#    So a composite classification code comprising family and model may be tractable.
#    So there is merit in investigating this.
#    
# 3. The benefit of doing so, is that there are 36 model records which are purely numeric.
#    The family column will be needed to avoid spurious matches.
# 
# 4. To think about... 
#    Can the family and model simply be concatenated (with a space between them)?
#    Or should there be a special separate character? e.g. '+'
#


# ----------------------------------------------------------------------
# 6.2 Perform the classification on the family column:
# 

family_block_pairs = products['family'].fillna('').apply(get_blocks_and_classification_tuple)
family_blocks, family_classifications = zip(* family_block_pairs )
products['family_blocks'] = family_blocks
products['family_classification'] = family_classifications

# check:
products.family_classification.value_counts()

# a      427
#        258
# a-a     43
# a_a      9
# a_       6


# ----------------------------------------------------------------------
# 6.3 Create a composite classification:
# 

products['family_and_model'] = products.family.fillna('') + ' + ' + products.model.fillna('')
products['family_and_model_len'] = products.apply(lambda prd: len(prd['family_and_model']) - 3, axis = 1).astype(np.object)
    # i.e. include the length of family and model, but without the joining characters: ' + '
    # NB: Convert to object data type, otherwise we start getting errors like this: 
    # "ValueError: Shape of passed values is (743,), indices imply (743, 13)"
products['composite_classification'] = products.family_classification + '+' + products.model_classification

# Concatenate the family and model blocks (with a joining block so that slices match up):
def get_composite_blocks(prod_row):
    family_blocks = prod_row['family_blocks']
    model_blocks = prod_row['model_blocks']
    blocks = list(family_blocks)
    blocks.append('+')
    blocks.extend(model_blocks)
    return blocks

products['blocks'] = products.apply(get_composite_blocks, axis=1)

group_and_save_classification_patterns('family_and_model', 'composite_classification', ['manufacturer','family','model','composite_classification','family_blocks','model_blocks', 'blocks'], 'composite_classifications')

# All composite classifications:
# 
# Pattern: +a              count: 2      example:  + Digilux
# Pattern: +a-a            count: 2      example:  + K-r
# Pattern: +a-a_n          count: 2      example:  + V-LUX 20
# Pattern: +a-an           count: 11     example:  + PDR-M60
# Pattern: +a-an!an        count: 1      example:  + DSC-V100 / X100
# Pattern: +a-ana          count: 2      example:  + R-D1x
# Pattern: +a-n            count: 41     example:  + FE-5010
# Pattern: +a-n_a          count: 17     example:  + C-2000 Zoom
# Pattern: +a-n_c          count: 2      example:  + C-2500 L
# Pattern: +a-na           count: 21     example:  + QV-5000SX
# Pattern: +a-na_a_a       count: 1      example:  + EOS-1D Mark IV
# Pattern: +a_a-an         count: 4      example:  + PEN E-P2
# Pattern: +a_a-ana        count: 1      example:  + PEN E-PL1s
# Pattern: +a_a_n          count: 7      example:  + mju Tough 8010
# Pattern: +a_an           count: 1      example:  + Kiss X4
# Pattern: +a_n            count: 7      example:  + mju 9010
# Pattern: +a_na           count: 1      example:  + mju 550WP
# Pattern: +an             count: 112    example:  + TL240
# Pattern: +an_a           count: 2      example:  + DC200 plus
# Pattern: +an_c           count: 1      example:  + X560 WP
# Pattern: +ana            count: 17     example:  + HZ15W
# Pattern: +c(an)          count: 1      example:  + GXR (A12)
# Pattern: +c_a            count: 1      example:  + N Digital
# Pattern: +c_a_a          count: 1      example:  + GR Digital III
# Pattern: a+a             count: 2      example: Digilux + Zoom
# Pattern: a+a-an          count: 119    example: Exilim + EX-Z29
# Pattern: a+a-ana         count: 3      example: Cybershot + DSC-HX100v
# Pattern: a+a-n           count: 15     example: Alpha + NEX-3
# Pattern: a+a-n_c         count: 1      example: Optio + WG-1 GPS
# Pattern: a+a_a_an        count: 1      example: EOS + Kiss Digital X3
# Pattern: a+a_an          count: 2      example: EasyShare + Mini M200
# Pattern: a+a_n           count: 5      example: Stylus + Tough 6000
# Pattern: a+a_n_a         count: 2      example: DiMAGE + EX 1500 Zoom
# Pattern: a+an            count: 159    example: Coolpix + S6100
# Pattern: a+an_a          count: 29     example: PowerShot + SD980 IS
# Pattern: a+an_ax         count: 1      example: ePhoto + CL30 Clik!
# Pattern: a+an_c          count: 2      example: PowerShot + SX220 HS
# Pattern: a+ana           count: 20     example: Finepix + Z900EXR
# Pattern: a+n             count: 35     example: FinePix + 1500
# Pattern: a+n.n           count: 1      example: Digilux + 4.3
# Pattern: a+n_a           count: 8      example: FinePix + 4700 Zoom
# Pattern: a+n_c           count: 7      example: IXUS + 310 HS
# Pattern: a+na            count: 15     example: Coolpix + 900S
# Pattern: a-a+a-an        count: 37     example: Cyber-shot + DSC-W310
# Pattern: a-a+a-ana       count: 5      example: Cyber-shot + DSC-HX7v
# Pattern: a-a+n           count: 1      example: D-LUX + 5
# Pattern: a_+an           count: 6      example: Cybershot  + W580
# Pattern: a_a+n_a         count: 8      example: Digital IXUS + 130 IS
# Pattern: a_a+n_c         count: 1      example: Digital IXUS + 1000 HS
# 
# Note: Now we're at 49 classification patterns (up from 32).
# 

# ----------------------------------------------------------------------
# All composite classifications after a refactoring to treat an 'x'
# followed by a digit (but not preceded by a dash) as 'xn' not 'an':
# 
# Pattern: +a              count: 2      example:  + Digilux
# Pattern: +a-a            count: 2      example:  + K-r
# Pattern: +a-a_n          count: 2      example:  + V-LUX 20
# Pattern: +a-an           count: 11     example:  + PDR-M60
# Pattern: +a-an!xn        count: 1      example:  + DSC-V100 / X100
# Pattern: +a-ana          count: 2      example:  + R-D1x
# Pattern: +a-n            count: 41     example:  + FE-5010
# Pattern: +a-n_a          count: 17     example:  + C-2000 Zoom
# Pattern: +a-n_c          count: 2      example:  + C-2500 L
# Pattern: +a-na           count: 21     example:  + QV-5000SX
# Pattern: +a-na_a_a       count: 1      example:  + EOS-1D Mark IV
# Pattern: +a_a-an         count: 4      example:  + PEN E-P2
# Pattern: +a_a-ana        count: 1      example:  + PEN E-PL1s
# Pattern: +a_a_n          count: 7      example:  + mju Tough 8010
# Pattern: +a_n            count: 7      example:  + mju 9010
# Pattern: +a_na           count: 1      example:  + mju 550WP
# Pattern: +a_xn           count: 1      example:  + Kiss X4
# Pattern: +an             count: 109    example:  + TL240
# Pattern: +an_a           count: 2      example:  + DC200 plus
# Pattern: +ana            count: 17     example:  + HZ15W
# Pattern: +c(an)          count: 1      example:  + GXR (A12)
# Pattern: +c_a            count: 1      example:  + N Digital
# Pattern: +c_a_a          count: 1      example:  + GR Digital III
# Pattern: +xn             count: 3      example:  + X70
# Pattern: +xn_c           count: 1      example:  + X560 WP
# Pattern: a+a             count: 2      example: Digilux + Zoom
# Pattern: a+a-an          count: 119    example: Exilim + EX-Z29
# Pattern: a+a-ana         count: 3      example: Cybershot + DSC-HX100v
# Pattern: a+a-n           count: 15     example: Alpha + NEX-3
# Pattern: a+a-n_c         count: 1      example: Optio + WG-1 GPS
# Pattern: a+a_a_xn        count: 1      example: EOS + Kiss Digital X3
# Pattern: a+a_an          count: 2      example: EasyShare + Mini M200
# Pattern: a+a_n           count: 5      example: Stylus + Tough 6000
# Pattern: a+a_n_a         count: 2      example: DiMAGE + EX 1500 Zoom
# Pattern: a+an            count: 158    example: Coolpix + S6100
# Pattern: a+an_a          count: 29     example: PowerShot + SD980 IS
# Pattern: a+an_a#         count: 1      example: ePhoto + CL30 Clik!
# Pattern: a+an_c          count: 2      example: PowerShot + SX220 HS
# Pattern: a+ana           count: 20     example: Finepix + Z900EXR
# Pattern: a+n             count: 35     example: FinePix + 1500
# Pattern: a+n.n           count: 1      example: Digilux + 4.3
# Pattern: a+n_a           count: 8      example: FinePix + 4700 Zoom
# Pattern: a+n_c           count: 7      example: IXUS + 310 HS
# Pattern: a+na            count: 15     example: Coolpix + 900S
# Pattern: a+xn            count: 1      example: FinePix + X100
# Pattern: a-a+a-an        count: 37     example: Cyber-shot + DSC-W310
# Pattern: a-a+a-ana       count: 5      example: Cyber-shot + DSC-HX7v
# Pattern: a-a+n           count: 1      example: D-LUX + 5
# Pattern: a_+an           count: 6      example: Cybershot  + W580
# Pattern: a_a+n_a         count: 8      example: Digital IXUS + 130 IS
# Pattern: a_a+n_c         count: 1      example: Digital IXUS + 1000 HS
# 
# Increased to 51 classification patterns.
# 

# ==============================================================================
# 7. Design matching rules based on the classification patterns:
# 
# Goal: 
# -----
# 
# Create a small set of rules that can be used to match these 49 patterns 
#       (and others that could arise with a different data set).
# ______________________________________________________________________________
# 
# Envisioned approach: 
# --------------------
# 
#   1. Create a number of matching regular expressions, 
#      with a numerical value for each, based on the value of that match.
#      
#   2. Some patterns are alternatives to each other, with the highest value being chosen:
#      e.g. match on family + model
#               then model only
#               then exact product code only
#               then alternative product code with optional dashes or spaces between parts of the code
#               then a product code and the next word 
#                   (so that 130IS can be matched as well as "130 IS").
#               then a product code and the first character of the next word 
#                   (so that "4700z" can be matched as well as "4700 Zoom").
#      
#   3. Others are additive
#      e.g. value of product code
#         + value/s of finding other words in the title (such as IS or Zoom or the Family)
#      
#      NB: A complication here is that the additive value will only be applicable 
#          for some of the previous patterns.
#      
#   4. For each listing:
#        For each product (filtered by the listing's manufacturer):
#          Calculate the highest value match (if any)
#            Notes:
#                i. A threshold can be chosen with values below the threshold being ignored.
#               ii. Match against the listing's productDesc first, 
#                   then against extraProdDetails (with very low value)
#        Sort the list matching products
#        If exactly one match, or one match that is sufficiently above the rest, make this the final match.
#        Otherwise, if there are multiple matches, flag for further investigation (to identify possible new rules).
#        
#   5. Use flagged listings to generate new matching rules. 
#      Repeat this process until further improvement is either not possible or not desirable.
#      
#   6. Invert the relationship between listings and chosen products.
#        Group listings by the chosen products for each listing.
#        Add a listings columns to the products data frame and populate it from the grouped data.
#      
#   7. Output the list of products with their listings.
# ______________________________________________________________________________
# 
# Reality check:
# --------------
# 
# But first...
# 1. Is this the right approach? 
# 2. Are there reasons why it won't work?
# 3. Is there a way to test the approach cheaply?
# 4. Is there a simpler way?
#    e.g. match on product code only
# 5. Is Python the best way to build the rules engine?
# 6. Would a functional language work better?
#    (e.g. due to the pattern matching capabilities, or through using a parser-combinator library)
# 


# ----------------------------------------------------------------------
# 7.1 Can we match on product code only?
#

# An example where this is not sufficient...
products[products.model.str.contains('EOS-1D')][['manufacturer','family','model']]
#     manufacturer family           model
# 624        Canon    NaN  EOS-1D Mark IV

listings[listings.title.str.contains('EOS-1D')].title.head()
# 1505    Canon EOS-1D 4.15MP Digital SLR Camera (Body O...
# 1550    Canon EOS-1D Mark II 8.2MP Digital SLR Camera ...
# 1551    Canon EOS-1D Mark II 8.2MP Digital SLR Camera ...
# 1629    Canon EOS-1Ds 11.1MP Digital SLR Camera (Body ...
# 8639              Canon EOS-1D MARK IV Digital SLR Camera

# So in this case there are multiple products sharing the same base product code.

# This particular example can be fixed by an exception condition, as there is only one product with Mark in its title...
products[products.model.str.contains('mark')][['manufacturer','family','model']]
products[products.model.str.contains('Mark')][['manufacturer','family','model']]
#     manufacturer family           model
# 624        Canon    NaN  EOS-1D Mark IV


# To think about: are there other exceptions? How can we identify them?


# --------------------------------------------------------------------------
# 7.2 Further thoughts on the EOS1-D issue:
# 
# After a wonderful Saturday afternoon sleep, I had a possible epiphany:
# 
# Look at the listings for the EOS1-D above.
# It's easy to see that they are different products - they have different mega-pixel ratings.
# This suggests a way to address the issue of multiple products sharing a product code
# without resorting to product-specific rules (and improve the algorithm at the same time) ...
# 
# For each listing, extract product specifications (such as the Megapixel rating).
# For each product, find a listing which is an exact or very close match, 
# and use its specifications as the product's specifications.
# Reject any listings which have different specifications.

# Let's see if this would work for the EOS 1-D Mark IV:

# After some fiddling, the following pattern found a few listings...
listingsByPManuf[listingsByPManuf.productDesc.str.contains('1D\s+MARK\s+IV', flags=re.IGNORECASE)].title

# 4149    Canon EOS 1D Mark IV 16.1 MP CMOS Digital SLR ...
# 5245              Canon EOS-1D MARK IV Digital SLR Camera
# 5246              Canon EOS-1D MARK IV Digital SLR Camera
# 6347    Canon - EOS-1D Mark IV - Appareil photo reflex...
# 6348    Canon - EOS-1D Mark IV - Appareil photo reflex...

# Example of extracting a specification:
mpPattern = '(\d+(?:[.,]\d+)?)\s*(?:\-\s*)?(?:MP|MPixe?l?s?|(?:(?:mega?|mio\.?)(?:|\-|\s+)pix?e?l?s?))(?:$|\W)'

listingsByPManuf[
    listingsByPManuf.productDesc.str.contains('1D\s+MARK\s+IV', flags=re.IGNORECASE)
].productDesc.str.findall(mpPattern, flags=re.IGNORECASE)
# 4149    [16.1]
# 5245        []
# 5246        []
# 6347        []
# 6348        []

listingsByPManuf[
    listingsByPManuf.productDesc.str.contains('1D\s+MARK\s+IV', flags=re.IGNORECASE)
].productDesc.str.findall(mpPattern, flags=re.IGNORECASE).str.get(0)
# 4149    16.1
# 5245     NaN
# 5246     NaN
# 6347     NaN
# 6348     NaN

# Conclusions:
# 
# 1. This approach appears feasible. A listing can be automatically excluded 
#    if any of its specifications don't match the product's corresponding specification.
#    
# 2. Don't use the closest match - it may not have a specification. 
#    Instead use any sufficiently close match which has the specification.
#    
# 3. Many listings don't have a mega-pixel specification, so:
#    a. It may not be possible to determine a particular specification for the product 
#       i.e. no sufficiently close match had the specification
#    b. Many listings may not have the specification.
#       How to decide whether to exclude them or include them?
#       What is a sufficiently close match to not require the specification?
#    
# 4. This is getting pretty complex.
#    Could this be a rabbit-hole?
#    Or is the complexity essential?
#    
# 5. My original strategy was to match on product codes, since these are 
#    fairly domain-agnostic. Building in some domain logic does make some sense,
#    but it can be a rabbit-hole. Beware of diminishing returns!
#
# 6. What technical specifications make the most sense to match on?
#    


# --------------------------------------------------------------------------
# 7.3 Determine mega-pixel specifications
# 
listingsByPManuf[listingsByPManuf.productDesc.str.contains('meg')].productDesc

# 87             SAMSUNG ES15 10.2 megapixel camera (SILVER)
# 341      Samsung ST80 Black 14.2-megapixel Digital Came...
# 615      Samsung D1070 10.2 mega-pixels 3x optical zoom...
# 9253     Panasonic DMC-FX07EB Digital Camera [7.2 megap...
# 11055    Sony DSCV1 Digital Camera 5megapixel 4 X Zm Night
# 19845       HP Photosmart R717 Digitalkamera (6 megapixel)

# Action: Updated mpPattern above
def convert_mp_to_float(s):
    if isinstance(s, float):
        return s 
    else:
        return float(s.replace(',','.'))

listingsByPManuf['resolution_in_MP'] = \
    listingsByPManuf.productDesc.str.findall(mpPattern, flags=re.IGNORECASE).str.get(0).apply(convert_mp_to_float)
listingsByPManuf['rounded_MP'] \
    = listingsByPManuf.resolution_in_MP[listingsByPManuf.resolution_in_MP.notnull()].apply(lambda mp: floor(mp))

# listingsByPManuf
# 
# <class 'pandas.core.frame.DataFrame'>
# Int64Index: 16785 entries, 5 to 20195
# Data columns (total 9 columns):
# pManuf              16785  non-null values
# lManuf              16785  non-null values
# title               16785  non-null values
# currency            16785  non-null values
# price               16785  non-null values
# productDesc         16785  non-null values
# extraProdDetails    7587  non-null values
# resolution_in_MP    13366  non-null values
# rounded_MP          13366  non-null values
# dtypes: float64(2), object(7)
#
# Result: 80% of listings have a MP resolution field (13366 / 16785)


# -----------------------------------------------------------------------------------------------
# Strategy to evaluate the technical specification approach without "going down the rabbit-hole":
# 
# 1. Don't generate any other specifications yet.
# 2. Add code to get "exact" matches on entire product name
#    (but with optional whitespace and dashes between the characters).
# 3. Add code to get a list of "exact match" listings per product.
# 4. See if any products have conflicting technical specifications (mega-pixels) amongst their exact match listings.
#    If so, investigate and adjust the approach.
# 5. Add code to use the exact matches to determine mega-pixel specifications for products.
# 6. Develop algorithm to match on product codes, and get listings per product based on product code matches.
# 7. See how many of these listings would get rejected due to mismatched technical specifications.
# 8. Decide on this basis whether there is value in extracting other technical specifications to filter matches.


# --------------------------------------------------------------------------
# 7.4 Find "exact" matches
# 
# These have all the alphanumeric characters from manufacturer (optional), family and model
# in sequence, but with optional whitespace and dashes between every pair of adjacent characters.

def regex_escape_with_optional_dashes_and_whitespace(text):
    # Remove all white-space and dashes:
    escaped_text = re.sub('(\s|\-)+', '', text)
    is_last_char_numeric = len(escaped_text) > 0 and escaped_text[-1].isdigit()
    # Insert a dash after every character.
    # Note: this is just a place-holder for where a regex will be inserted later.
    escaped_text = '-'.join(escaped_text)
    escaped_text = re.escape(escaped_text)
    # Replace the "\-" place-holder with a regex sequence matching whitespace characters and/or a single dash:
    escaped_text = re.sub(r'\\\-', r'\s*(?:\-\s*)?', escaped_text)
    # Do negative lookbehind to ensure this is not in the middle of a word:
    escaped_text = r'(?<!\w)' + escaped_text
    # Do negative lookahead:
    if is_last_char_numeric:
        # Don't match a final numeric character if it's followed by a decimal point (or comma) and a number.
        # This is to prevent issues like a "Casio Exilim EX-Z3 3.2MP Digital Camera" being a match for an "EX-Z33" model.
        escaped_text = escaped_text + r'(?!\w|\-|\.\d|\,\d)'
    else:
        escaped_text = escaped_text + r'(?!\w|\-)'
    return escaped_text

# This works better than the first attempt...
# 
# text = 'EOS   -\t1-D'
# esc_text = regex_escape_with_optional_dashes_and_whitespace(text)
# esc_text
# Out: 'E\\s*(?:\\-\\s*)?O\\s*(?:\\-\\s*)?S\\s*(?:\\-\\s*)?1\\s*(?:\\-\\s*)?D'
# re.search(esc_text, 'EO-S 1 - D ', flags = re.IGNORECASE or re.UNICODE) != None
# Out: True

def generate_exact_match_pattern(family, model):
    fam_and_model = family + model
    fam_and_model_pattern = regex_escape_with_optional_dashes_and_whitespace(fam_and_model)
    return fam_and_model_pattern

def generate_exact_match_regex_and_pattern(products_row):
    'Assumption: null/na values in the family column have been converted to empty strings'
    family = products_row['family']
    model = products_row['model']
    pattern = generate_exact_match_pattern( family, model)
    regex = re.compile( pattern, flags = re.IGNORECASE or re.UNICODE )
    return regex, pattern

regex_pattern_pairs = products.fillna({'family': ''}).apply(generate_exact_match_regex_and_pattern, axis=1)
exact_match_regexes, exact_match_patterns = zip(* regex_pattern_pairs )

products['exact_match_regex'] = exact_match_regexes
products['exact_match_pattern'] = exact_match_patterns

# Perform join between products and listings by product:
products_to_match = products.reset_index()[['index', 'manufacturer', 'family', 'model', 'exact_match_regex']]
listings_to_match = listingsByPManuf.reset_index()[['index', 'pManuf', 'productDesc', 'extraProdDetails', 'resolution_in_MP', 'rounded_MP', 'original_listing_index']]

products_and_listings = pd.merge(left=listings_to_match, right=products_to_match, how='inner', left_on='pManuf', right_on='manufacturer', suffixes=('_l','_p'))

def is_exact_match(p_and_l_row):
    product_desc = p_and_l_row['productDesc']
    regex = p_and_l_row['exact_match_regex']
    return regex.search(product_desc) != None

products_and_listings['is_exact_match'] = products_and_listings.apply(is_exact_match, axis=1)
# NB: This is slow... duration measured with %time:
#
# CPU times: user 21.35 s, sys: 0.00 s, total: 21.35 s
# Wall time: 21.36 s
# 

exact_match_columns = ['index_l', 'productDesc', 'resolution_in_MP', 'rounded_MP', 'index_p', 'manufacturer', 'family', 'model']
exact_matches = products_and_listings[products_and_listings.is_exact_match][exact_match_columns]


# --------------------------------------------------------------------------
# 7.5 Determine technical specification (resolution in MP) 
#     for the product from the exact matches:
# 

# Arbitrary rule: 
#     75% of listings must share the same resolution (megapixels) for it to become the product's resolution:
THRESHOLD_PRODUCT_RESOLUTION_RATIO = 0.75

def analyze_matches(grp):
    ind_p = grp.iloc[0]['index_p']
    vc = grp.rounded_MP.value_counts()
    unique_count = vc.count()
    
    if unique_count == 0:
        product_resolution = np.NaN
    else:
        total_count = vc.sum()
        most_common_count = vc.order(ascending=False).iget_value(0)
        
        if (unique_count > 0) and (truediv(most_common_count, total_count) >= THRESHOLD_PRODUCT_RESOLUTION_RATIO):
            product_resolution = vc.order(ascending=False).index[0]
        else:
            product_resolution = np.NaN
    
    return ind_p, unique_count, product_resolution

exact_match_groups = exact_matches.groupby('index_p')
product_resolution_tuples = exact_match_groups.apply(analyze_matches)

ind_ps, product_resolution_unique_counts, product_resolutions = zip(* product_resolution_tuples )

exact_match_df = DataFrame( 
    { 'resolution_in_MP_unique_count': product_resolution_unique_counts, 
      'product_resolution_in_MP': product_resolutions
    }, index = ind_ps)

products = pd.merge(products, exact_match_df, how='outer', left_index=True, right_index=True)

# Check:
# products[products.resolution_in_MP_unique_count > 1][['manufacturer', 'family', 'model', 'product_resolution_in_MP', 'resolution_in_MP_unique_count']]



# --------------------------------------------------------------------------
# 7.6 Investigate exact matches with conflicting mega-pixel specifications:
# 

# Write conflicting matches to a data file for further investigation:
conflicting_spec_prod_indexes = exact_match_df[exact_match_df.resolution_in_MP_unique_count > 1]
conflicting_exact_matches = pd.merge(conflicting_spec_prod_indexes, exact_matches, left_index=True, right_on='index_p', how='inner')
conflicting_exact_matches = conflicting_exact_matches[conflicting_exact_matches.resolution_in_MP.notnull()]
conflicting_exact_matches[['manufacturer', 'family', 'model', 'product_resolution_in_MP', 'productDesc', 'rounded_MP', 'resolution_in_MP']]\
    .to_csv('../data/intermediate/conflicting_exact_matches.csv', encoding='utf-8')

# Some discoveries from looking at the data file:
# 
# 1. MPix is also a shortening for Megapixels.
# 2. Megapixel ratings are being filtered out if the succeeding character is '(', ';', etc.
# 3. Megapixel ratings can contain a ',' as a radix point as well.
# 4. Some listings round down the mega-pixel rating. Rather compare on the rounded figure.
# 5. Filter out listings without a mega-pixel rating when reporting deviations.
# 6. Remember to check for listings that match more than 1 product, as these will show other deviations.
# 7. What to do about the DIGILUX matches (see below)? 

# An example of a listing where the MegaPixel ratings genuinely differ:
# 
# productDesc                              resolution_in_MP
# Leica DIGILUX 3 7.5MP Digital SLR Camera 7.5
# Leica DIGILUX 3 7.5MP Digital SLR Camera 7.5
# Leica 'Digilux 2' 5MP Digital Camera     5
# Leica 'Digilux 2' 5MP Digital Camera     5
# Leica Digilux 4.3 2.4MP Digital Camera   2.4
# Leica Digilux 1 3.9MP Digital Camera     3.9
# 

# ------------------------------------------------------
# Further discoveries after fixing some of these issues:
# 
# 8. Some unmatched values use "mio"/"mio." pixels (mostly German listings). Is this the same as mega-pixels? 
# 9. Sometimes just an M is used to indicated mega-pixels
#    e.g. Canon PowerShot SX30 IS - 1/2.3 type CCD; 14.1M; DIGIC 4; 35x zoom; IS; (2.7) PureColor II VA (TFT)Hi-Speed USB (MTP; PTP) (4344B009AA)
# 

# Answers:
# 8. mio is short for millions in Germany. Added to regex pattern.
# 9. Ignore patterns like 14.1M. Better than risking an incorrect match.
# 10. Some data records are clearly errors. Others are because the data is not selective enough.
#    Consider the Leica DigiLux records shown above. 
#    Choosing the most common resolution as the product's resolution is not correct.
#    
#    Action: Only set the product's resolution if at least 75% of the records have that resolution.
#
#    Consideration: This could still be incorrect. 
#                   The records that contribute the 75% could be matching to another product as well.
#                   TODO: Develop an algorithm/approach for dealing with listings that match multiple products.


# --------------------------------------------------------------------
# Records which higlight some problems with the "exact match" pattern:
# 
# manufacturer  family  model   productDesc
# Casio         Exilim  EX-Z33  Casio Exilim EX-Z3 3.2MP Digital Camera
# Leica                 X1      Leica V-Lux-1 10 Megapixel Digital Camera
# Leica                 X1      Leica C-LUX 1 6MP Digital Camera
# Leica                 X1      Leica V-Lux-1 10 Megapixel Digital Camera
# Leica                 X1      Leica Digilux 1 3.9MP Digital Camera
# Fujifilm      FinePix Z35     Fujifilm Finepix Z3 5.1MP Digital Camera
# 
# ________________________________
# 
# Actions taken to address these issues:
# 
# 1. Modified negative lookahead pattern at the end of the exact match regex pattern.
#    
#    If the last character is numeric, don't allow the very next characters to be:
#    a. '.' + a digit
#    b. ',' + a digit
#    
# 2. Added a negative lookbehind to the front of the exact match regex pattern
#    to ensure that the first matched character is not in the middle of a word (or product code).
# 

# Determine the number and proportion of exact match records which can be rejected due to mismatched resolution (mega-pixels):
exact_matches_with_mp = pd.merge(exact_matches, exact_match_df, how='outer', left_on='index_p', right_index=True)

exact_matches_with_mp.product_resolution_in_MP.count()
# 7495 records

exact_matches_with_mp[
  exact_matches_with_mp.rounded_MP.notnull() 
  & exact_matches_with_mp.product_resolution_in_MP.notnull()].rounded_MP.count()
# 5795

excluded_by_MP = exact_matches_with_mp[
  exact_matches_with_mp.rounded_MP.notnull() 
  & exact_matches_with_mp.product_resolution_in_MP.notnull() 
  & (exact_matches_with_mp.product_resolution_in_MP != exact_matches_with_mp.rounded_MP)]

excluded_by_MP[['manufacturer', 'family', 'model', 'product_resolution_in_MP', 'productDesc', 'rounded_MP', 'resolution_in_MP']]
# 10 records

# So filtering exact matches by mega-pixel resolutions has found just 10 records to reject out of almost 6 000.
# Furthermore, most of these 10 listings ARE matched to the correct product. They just have a typo in the data.
# 
# This isn't very promising. However these are the products which had more than 75% consensus on the resolution.
# The more controversial records are not included yet, and that may be where resolution matching has greater value.
# 
# But regardless of whether it will be useful in the final algorithm, it has already proved very useful for testing the code.


# -----------------------------------------------------------------------------
#
# At this point the script was becoming too cumbersome.
# A more powerful approach was needed.
# 
# So create an object-oriented solution to:
# 
# a. Turn classifications into rule templates
# b. Use the rule templates to generate a sequence of patterns to match 
#    (e.g. based on regular expressions), of diminishing value.
# c. Use a value function to estimate the quality of the match
# d. Join listings to products to determine the value of the match between them.
# e. Determine the highest value match for each listing to determine its product.
# f. First check that this produces the same results as before 
#    when doing regex matching on family + model.
# g. Add other patterns as well
# h. Determine how slow
# i. If too slow, add code to interleave products' matching engine calculations
#    in approximate value order. Then stop further matching when a product matches, 
#    and no other product can get a higher match any more.
#    


# ==============================================================================
# 8. Load matching engine and matching rule classes to calculate 
#    highest value matches between products and listings:
# 
#
from recordlinker.classification import *
from recordlinker.builder import *

unique_classifications = products.composite_classification.unique()


# ==============================================================================
# 9. Test matching engine and matching rule classes by calculating
#    the highest value matches between products and listings
#    using only the family-and-model approximate (regex) matching method.
#    Then compare this to the ad hoc "exact match" algorithm used previously.
#


# -----------------------------------------------------------------------------
# 9.1 Generate a test master template for each classification:
# 

class TestMasterTemplateBuilder(BaseMasterTemplateBuilder):
    def get_listing_templates(self):
        return self.generate_listing_templates_from_methods([BaseMasterTemplateBuilder.match_all_of_family_and_model_with_regex])

test_master_template_dict = {
    classification: TestMasterTemplateBuilder(classification).build()
    for classification in unique_classifications 
}

# -----------------------------------------------------------------------------
# 9.2 Generate a test matching engine for each product:
# 
def generate_test_matching_engine(prod_row):
    classification = prod_row['composite_classification']
    blocks = prod_row['blocks']
    family_and_model_len = prod_row['family_and_model_len']
    master_template = test_master_template_dict[classification]
    engine = master_template.generate(blocks, family_and_model_len)
    return engine

products['test_matching_engine'] = products.apply(generate_test_matching_engine, axis=1)

# -----------------------------------------------------------------------------
# 9.3 Add engine to each row of products_and_listings:
#       

products_and_listings_test = pd.merge(products_and_listings, products[['test_matching_engine']], left_on='index_p', right_index=True, how='inner')
    
# -----------------------------------------------------------------------------
# 9.4 Run the test matching engine for each product and listing combination:
# 

def run_test_matching_engine(p_and_l_row):
    product_desc = p_and_l_row['productDesc']
    extra_prod_details = p_and_l_row['extraProdDetails']
    engine = p_and_l_row['test_matching_engine']
    match_result = engine.try_match_listing(product_desc, extra_prod_details)
    return match_result

test_match_results = products_and_listings_test.apply(run_test_matching_engine, axis=1)

products_and_listings_test['match_result'] = test_match_results
products_and_listings_test['match_result_is_match'] = products_and_listings_test['match_result'].map(lambda mr: mr.is_match)
products_and_listings_test['match_result_value'] = products_and_listings_test['match_result'].map(lambda mr: mr.match_value)
products_and_listings_test['match_result_description'] = products_and_listings_test['match_result'].map(lambda mr: mr.description)

# -----------------------------------------------------------------------------
# 9.5 Compare the results of the test matching engine 
#     with the original ad hoc match results:
# 

# products_and_listings_test[products_and_listings_test.match_result_is_match == True].head()

test_engine_mismatches = products_and_listings_test[products_and_listings_test.match_result_is_match != products_and_listings_test.is_exact_match]
test_engine_mismatches

# Success! There are no differences. 
# So the class-based method runs successfully and produces the same results as the original ad hoc method!


# -----------------------------------------------------------------------------
# 9.6 Clean up:
#
# Free up memory - due to occasionally getting a "MemoryError"
# 
del products_and_listings_test
del test_match_results
del test_engine_mismatches



# ==============================================================================
# 10. Use the matching engine and matching rule classes to calculate 
#     highest value matches between products and listings:
# 
#

# -----------------------------------------------------------------------------
# 10.1 Generate a master template for each classification:
# 
master_template_dict = {
    classification: MasterTemplateBuilder(classification).build() 
    for classification in unique_classifications 
}

# -----------------------------------------------------------------------------
# 10.2 Generate a matching engine for each product:
# 
def generate_matching_engine(prod_row):
    classification = prod_row['composite_classification']
    blocks = prod_row['blocks']
    family_and_model_len = prod_row['family_and_model_len']
    master_template = master_template_dict[classification]
    engine = master_template.generate(blocks, family_and_model_len)
    return engine

products['matching_engine'] = products.apply(generate_matching_engine, axis=1)

# -----------------------------------------------------------------------------
# 10.3 Add engine to each row of products_and_listings:
# 
# Note: Ideally this should be done when products_and_listings is created.
#       However we didn't have the matching engine classes then.
#       
#       TODO: refactor this into the correct place for the final solution.
# 

products_and_listings = pd.merge(products_and_listings, products[products.matchRule != 'ignore'][['matching_engine']], left_on='index_p', right_index=True, how='inner')

# Note: This was modified after the fact to filter by product.matchRule. See discovery 5 under section 10.5 below.

# -----------------------------------------------------------------------------
# 10.4 Run the matching engine for each product and listing combination:
# 

def run_matching_engine(p_and_l_row):
    product_desc = p_and_l_row['productDesc']
    extra_prod_details = p_and_l_row['extraProdDetails']
    engine = p_and_l_row['matching_engine']
    match_result = engine.try_match_listing(product_desc, extra_prod_details)
    return match_result
    # Originally this was returning a tuple, but this didn't work.
    # Why not? This approach had worked fine elsewhere in the script...
    # return match_result.is_match, match_result.match_value, match_result.description

match_results = products_and_listings.apply(run_matching_engine, axis=1)

products_and_listings['match_result'] = match_results
products_and_listings['match_result_is_match'] = products_and_listings['match_result'].map(lambda mr: mr.is_match)
products_and_listings['match_result_value'] = products_and_listings['match_result'].map(lambda mr: mr.match_value)
products_and_listings['match_result_description'] = products_and_listings['match_result'].map(lambda mr: mr.description)

# Number of matches for each type of matching rule:
products_and_listings.match_result_description.value_counts()

# Results:
#                                                  1158086
# Family and model approximately                      7757
# Prod code with dash approximately                    473
# Family and model separately and approximately        343
# Prod code without a dash approximately               219
# Model and words in family approximately               46
#
# Check if the matches makes sense by inspection...
# 
# mr_description = 'Model and words in family approximately'
# products_and_listings[products_and_listings.match_result_description == mr_description][['productDesc','family','model','manufacturer']]
# 


# -----------------------------------------------------------------------------
# 10.5 Find listings which match more than one product:
# 

rule_match_columns = ['index_l', 'productDesc', 'resolution_in_MP', 'rounded_MP', 'index_p', 'manufacturer', 'family', 'model']
rule_matches = products_and_listings[products_and_listings.match_result_is_match][rule_match_columns]

matched_products_and_listings = products_and_listings[products_and_listings.match_result_is_match]
manuf_listing_groups = matched_products_and_listings.groupby(['manufacturer', 'index_l'])
manuf_listing_group_sizes = manuf_listing_groups.size()
manuf_listing_sizes = DataFrame({'group_count' : manuf_listing_group_sizes}).reset_index()
manuf_listing_dup_groups = manuf_listing_sizes[manuf_listing_sizes.group_count > 1]
manuf_listing_dups_columns = ['manufacturer','family','model','index_l','productDesc','extraProdDetails','match_result_is_match','match_result_value','match_result_description','group_count']
manuf_listing_dups = pd.merge(matched_products_and_listings, manuf_listing_dup_groups, on=['manufacturer','index_l'], sort=True)[manuf_listing_dups_columns]
manuf_listing_dups_sorted = manuf_listing_dups.sort_index(by = ['group_count','manufacturer','productDesc','index_l','match_result_value'], ascending=[False,True,True,True,False])
manuf_listing_dups_sorted.to_csv('../data/intermediate/manuf_listing_dups.csv', encoding='utf-8')

# Export matched listings, so that we can compare before and after to see which listings have been added:
matched_products_and_listings['index_l'].value_counts().sort_index().to_csv('../data/intermediate/matched_listing_indexes.csv', encoding='utf-8')


# ------------------------------------------------------------------------------------
# Discoveries:
# 
# matched_products_and_listings.index_l.count()
# 8847
# (i.e. total matched listings)
# 
# manuf_listing_dups_sorted.index_l.value_counts().count()
# 95
# (i.e. listings with more than one matching product).
#
# Script to extract a subset of the listings:
# 
# index_l_filter = 8211
# mlist_dups_sorted_min_columns = ['manufacturer', 'family','model','productDesc','match_result_value']
# manuf_listing_dups_sorted[manuf_listing_dups_sorted.index_l == index_l_filter][mlist_dups_sorted_min_columns]
# 
# The following anomalies were discovered in the data:
#
# ------------------------------------------------------------------------------------
# 
# 1. Dead heat between CL30 and CL30 Clik! products:
#   
#   manufacturer  family       model                   productDesc  match_result_value
# 0         Agfa  ePhoto  CL30 Clik!  Agfa CL30 1MP Digital Camera             1040000
# 1         Agfa  ePhoto        CL30  Agfa CL30 1MP Digital Camera             1040000
# 
# Possible corrective action: 
# 
# a. Subtract match value for words in listing which were not matched, or
# b. Favour shorter family and model by subtracting the length of family and model from the match value
#    (simpler and roughly equivalent).
#
# ------------------------------------------------------------------------------------
# 
# 2. Some listings have product descriptions containing alternate product codes.
#    The alternative product codes could be in brackets or after a slash (i.e. divider).
#    Which product is found depends on the longest code, not the best match.
#    This happened a lot for the Canon 550D/Rebel T2i/Kiss X4 products.
# 
# Example 2.1:
# 
#    manufacturer family    model                                        productDesc  match_result_value
# 33        Canon  Rebel      T2i  Canon KissX4 (European model:Canon Rebel T2i) ...            10900000
# 34        Canon    NaN  Kiss X4  Canon KissX4 (European model:Canon Rebel T2i) ...            10600000
#
# Example 2.2:
#
#    manufacturer family model                               productDesc  match_result_value
# 52        Canon    EOS  550D  Canon T2I / 550D 29 Piece Pro Deluxe Kit             1040000
# 51        Canon  Rebel   T2i  Canon T2I / 550D 29 Piece Pro Deluxe Kit             1030000
# 
# Example 2.3:
# 
#     manufacturer family   model                                        productDesc  match_result_value
# 182      Samsung    NaN  ST5000  3.5" Touch Screen LCD Samsung TL240/ST5000 Dig...            10600000
# 181      Samsung    NaN   TL240  3.5" Touch Screen LCD Samsung TL240/ST5000 Dig...            10500000
#
# 
# Possible corrective actions:
# 
# a. Reduce the value of matches if the matched part of the productDesc comes after an open bracket or a slash.
# b. Split the listing's title into 3 parts, not 2: 
#        productDesc, altProductDesc (after the slash or brackets) and extraProdDetails
#    Add a 3rd parameter to the MatchValueFunction based on altProductDesc.
# c. Increase the value of matches which are earlier in the listing.
#    Modify MatchValueFunction.evaluate() to be based on match position as well as match length.
#    Issue: How to find the right balance between match position and match length.
#           NB: There may be no "right" balance, since it is likely to be product-dependent.
# 
# ------------------------------------------------------------------------------------
# 
# 3. The "Olympus � 550 WP" could match either the "Stylus 550WP" or the "mju 550WP"
# 
# 
#     manufacturer  family      model                                        productDesc  match_result_value
# 109      Olympus     NaN  mju 550WP  Olympus - � 550 WP - Appareil photo compact nu...             1060000
# 110      Olympus  Stylus      550WP  Olympus - � 550 WP - Appareil photo compact nu...             1060000
# 
# 
# Possible corrective actions:
# 
# a. Convert � to be mju in the product listing before performing the match.
#    This is tantamount to hard-coding a rule for a specific product.
# b. When "mju" is encountered in the family or model, create a second rule to convert to "�".
#    BUT: This gets messy, because it can't be done at the template level, 
#         since this is based only on classification.
# c. Do nothing. These are the same product. Don't worry which one is matched.
# 
# 
# ------------------------------------------------------------------------------------
# 
# 4. The "Pentax Optio WG-1 GPS-Digitalkamera" doesn't treat GPS as being part of the code
#    since "GPS" is followed by a dash immediately.
#
#
#     manufacturer family     model                                        productDesc  match_result_value
# 156       Pentax  Optio      WG-1  Pentax Optio WG-1 GPS-Digitalkamera (14 Megapi...            11000000
# 155       Pentax  Optio  WG-1 GPS  Pentax Optio WG-1 GPS-Digitalkamera (14 Megapi...             3130500
# 
# 
# Possible corrective actions:
# 
# a. Modify the regular expression to allow dashes as the next character after the match.
#    Currently there are a number of restrictions on the match, such as ensuring that:
#      i.   it is followed by whitespace,
#      ii.  or is at the end of the string,
#      iii. or that if it ends in a dash, the dash is NOT IN THE MIDDLE OF A WORD,
#      iv.  or that if ends in a number, that number is not followed by a decimal point).
#    
#    So rule iii could be relaxed.
#    But the rule sounds reasonable. Should it really be relaxed to cater for this special case?
#    Perhaps try relaxing it and see if it has any side-effects.
# 
# 
# ------------------------------------------------------------------------------------
# 
# 5. The Samsung SL202 has multiple product listings.
# 
# One of many examples:
# 
#     manufacturer family  model                          productDesc  match_result_value
# 165      Samsung    NaN  SL202  Samsung SL202 10.2MP Digital Camera            10500000
# 166      Samsung    NaN  SL202  Samsung SL202 10.2MP Digital Camera            10500000
# 
# Possible corrective actions:
# 
# a. This duplication was discovered much earlier.
#    To fix this, filter out products which have: matchRule == 'ignore'
# 
# 
# ------------------------------------------------------------------------------------

# ************************************************************************************
# 
# RESULTS OF MAKING SOME OF THESE PROPOSED CHANGES:
# 
# Proposal 4.a: Modify matches to allow a dash at the end of the match.
# 
# matched_products_and_listings.index_l.count()
# 8853
# (i.e. 6 extra listings matched)
# 
# 
# What are the extra matched listings?
# 
# index_l: 8528, 8529, 8949, 11767, 11780, 11781
#
# 
# new_index_l = 8528
# mlist_dups_sorted_min_columns = ['manufacturer', 'family','model','productDesc','match_result_value']
# matched_products_and_listings[matched_products_and_listings.index_l == new_index_l][mlist_dups_sorted_min_columns]
#
#        manufacturer family    model                                          productDesc  match_result_value
# 684914    Panasonic  Lumix  DMC-GH1    Panasonic DMC-GH1-K 12.1MP Four Thirds Interch...             3210000
# 684994    Panasonic  Lumix  DMC-GH1    Panasonic DMC-GH1-K 12.1MP Four Thirds Interch...             3210000
# 718598    Panasonic  Lumix  DMC-FS12   Panasonic Lumix DMC-FS12-K - Digital camera - ...            11400000
# 967044         Sony  Alpha  DSLR-A550  Sony - DSLR-A550- Appareil photo reflex numriq...             3270000
# 968060         Sony  Alpha  DSLR-A850  Sony - DSLR-A850- Appareil photo reflex numriq...             3270000
# 968141         Sony  Alpha  DSLR-A850  Sony - DSLR-A850- Appareil photo reflex numriq...             3270000
# 
# The last 3 matches are additional correct matches resulting from allowing the dash.
# The first 3 matches above are an example of why there was a rule about not allowing a dash at the end of the matching text.
# HOWEVER, wikipedia indicates that the K suffix is for the model in black (see http://en.wikipedia.org/wiki/Panasonic_Lumix_DMC-GH1).
# Hence the only changes are all good.
# 
# Additionally the listings with duplicates are now in the correct order:
# 
#     manufacturer family     model                                        productDesc  match_result_value
# 155       Pentax  Optio  WG-1 GPS  Pentax Optio WG-1 GPS-Digitalkamera (14 Megapi...            11400000
# 156       Pentax  Optio      WG-1  Pentax Optio WG-1 GPS-Digitalkamera (14 Megapi...            11000000
# 
# ------------------------------------------------------------------------------------
#
# Proposal 5a: Filter products by matchRule != 'ignore'
# 
# Result: All the SL202 listings decreased from 2 to 1 matches.
# 
# NB: This also reduced the number of matched listings ('index_l') by 12 to 8841.
# 
# ------------------------------------------------------------------------------------
#
# Proposal 3c: Allow the "Olympus � 550 WP" to match either the "Stylus 550WP" or the "mju 550WP"
#              Do nothing.
# 
# Reason: http://en.wikipedia.org/wiki/Olympus_mju indicates that these are identical products differing by region.
#         Any attempt to fix this would require adding logic specific to this one match - not worth it.
# 
# Note: This might be fixed by proposal 1b (matching shortest model + family), since "mju 550WP" is shorter than "Stylus 550WP".
# 
# ------------------------------------------------------------------------------------
#
# Proposal 1b: Subtract length of family + model from each match.
# 
# Note: Unwanted side-effect... the length will be subtracted once per matching rule.
#       So when multiple words match, the total length gets subtracted repeatedly.
#       Since this should only be used as a tie-break condition, the repetitions shouldn't matter.
# 
# NB:   All value functions were scaled up by a factor of 100.
#       Hence the subtraction of the match length should be negligible compared to other factors.
# 
# Result:  Success! The only changed sequence was for the "Agfa CL30"
#          listing not to have a highest match for the "CL30 Clik!":
# 
#   manufacturer  family       model                   productDesc  match_result_value
# 1         Agfa  ePhoto        CL30  Agfa CL30 1MP Digital Camera           103999990
# 0         Agfa  ePhoto  CL30 Clik!  Agfa CL30 1MP Digital Camera           103999984
#
# 
# matched_products_and_listings.index_l.count()
# 8841
# 
# So no change in the number of matches.
# 
# 
# ------------------------------------------------------------------------------------
#
# Proposal 2c: Multiply the value of a listing if it is before 
#              the separator (slash or bracket) in the productDesc
# 
# Result: Success! 
#         Each of the listings for a variant of the Canon EOS 550D is now using the first product code in the listing.
#         The following listing was also out of sequence previously, and is now correct:
# 
#     manufacturer family   model                                        productDesc  match_result_value
# 161      Samsung    NaN   TL240  3.5" Touch Screen LCD Samsung TL240/ST5000 Dig...         10499999995
# 162      Samsung    NaN  ST5000  3.5" Touch Screen LCD Samsung TL240/ST5000 Dig...          1059999994
# 
# matched_products_and_listings.index_l.count()
# 8841
# 
# So no change in the number of matches.
# 


# -----------------------------------------------------------------------------
# 10.6 Find product with highest match value for each listing:
# 

def get_highest_value_product_for_listing(listing_grp):
    by_val = listing_grp.sort_index(by='match_result_value', ascending=False)
    return by_val.iloc[0]

matches_grouped_by_listing = matched_products_and_listings.groupby('index_l')
best_matches = matches_grouped_by_listing.apply(get_highest_value_product_for_listing)

best_match_columns = ['index_p', 'manufacturer', 'family', 'model', 'productDesc', 'extraProdDetails', 'match_result_value', 'match_result_description']
best_match_sort_by = ['manufacturer', 'family', 'model', 'productDesc', 'extraProdDetails']
best_matches[best_match_columns].sort_index(by=best_match_sort_by).to_csv('../data/intermediate/best_matches_by_match_result_value.csv', encoding='utf-8')

# Script to investigate particular listings:
# 
# index_l_filter = 6414
# best_matches_min_columns = ['manufacturer', 'family','model','productDesc','match_result_value']
# best_matches[best_matches.index_l == index_l_filter][best_matches_min_columns]
#


# ------------------------------------------------------------------------------------
# Discoveries from manually inspecting the matches:
# 
# 10.6.1. Why was ELPH 500 HS matched instead of Canon IXY 31S:
# 
# index_l  index_p  manufacturer  family   model  productDesc
# 5102         117         Canon    ELPH  500 HS  Canon IXY Digital camera IXY 31S Brown | ELPH 500 HS, IXUS 310 (Japan Import)
# 5084         117         Canon    ELPH  500 HS  Canon IXY Digital camera IXY 31S Gold | ELPH 500 HS, IXUS 310 (Japan Import)
# 5086         117         Canon    ELPH  500 HS  Canon IXY Digital camera IXY 31S Pink | ELPH 500 HS, IXUS 310 (Japan Import)
# 5089         117         Canon    ELPH  500 HS  Canon IXY Digital camera IXY 31S Silver | ELPH 500 HS, IXUS 310 (Japan Import)
#
# Answer:
# 
# There are no products with IXY in the model.
# 
# The only products with '31' in the model are found as follows, and there is no 31S:
# 
# products[products.model.str.contains('31')][['family','model']]
# 
#          family     model
# 0    Cyber-shot  DSC-W310
# 13         IXUS    310 HS
# 247         NaN     TG310
# 267     Coolpix     S3100
# 353   PowerShot  A3100 IS
# 393         NaN    DCS315
# 425  Photosmart      C315
# 529         NaN     D3100
# 539   EasyShare      M531
# 
# 
# Corrective action: None required.
# 
# --------------------------------------------------------------------------------------
# 10.6.2. Canon EOS 1-D Mark IV was also matched by the Mark I, II and II
# 
# index_l index_p  manufacturer  family           model  productDesc
# 6396        624         Canon          EOS-1D Mark IV  Canon EOS 1D Mark II - Appareil photo numérique - Reflex - 8.2 Mpix - boîtier nu - mémoire prise en charge : CF, SD, Microdrive - noir
# 6397        624         Canon          EOS-1D Mark IV  Canon EOS 1D Mark II - Appareil photo numérique - Reflex - 8.2 Mpix - boîtier nu - mémoire prise en charge : CF, SD, Microdrive - noir
# 4145        624         Canon          EOS-1D Mark IV  Canon EOS 1D Mark II N 8.2MP Digital SLR Camera (Body Only)
# 4594        624         Canon          EOS-1D Mark IV  Canon EOS 1D Mark III - Digital camera - SLR - 10.0 Mpix - body only - supported memory: CF, MMC, SD, Microdrive, SDHC
# 4595        624         Canon          EOS-1D Mark IV  Canon EOS 1D Mark III - Digital camera - SLR - 10.0 Mpix - body only - supported memory: CF, MMC, SD, Microdrive, SDHC
# 4177        624         Canon          EOS-1D Mark IV  Canon EOS 1D Mark III 10.1MP Digital SLR Camera (Body Only)
# 4178        624         Canon          EOS-1D Mark IV  Canon EOS 1D Mark III 10.1MP Digital SLR Camera (Body Only)
# 5313        624         Canon          EOS-1D Mark IV  Canon EOS 1D Mark III Digital SLR Camera (Body Only)
# 5314        624         Canon          EOS-1D Mark IV  Canon EOS 1D Mark III Digital SLR Camera (Body Only)
# 5315        624         Canon          EOS-1D Mark IV  Canon EOS 1D Mark III Digital SLR Camera (Body Only)
# 4168        624         Canon          EOS-1D Mark IV  Canon EOS-1D 4.15MP Digital SLR Camera (Body Only)
# 4175        624         Canon          EOS-1D Mark IV  Canon EOS-1D Mark II 8.2MP Digital SLR Camera (Body Only)
# 4176        624         Canon          EOS-1D Mark IV  Canon EOS-1D Mark II 8.2MP Digital SLR Camera (Body Only)
# 
# 
# Corrective action: 
# a. Calculate Megapixel rating of product using match values 
#    (e.g. using Bayesian average of match values with that mega-pixel value)
# b. Exclude all listings where the listing's mega-pixels don't match the product's.
# c. Re-calculate best product for each listing based on this filter.
# 
#
# --------------------------------------------------------------------------------------
# 10.6.3. Kiss X4 matched x4 optical zoom of the Powershot E1
# 
# index_l index_p manufacturer  family    model  productDesc
# 6259    627	         Canon          Kiss X4  Canon - PowerShot E1 - Appareil photo compact numérique - Capteur 10 MP - Zoom optique x4 - Stabilisateur - Rose
# 
# Corrective action:
# a. Don't allow a product code with a pattern of xn, x-n where n is numeric.
#    This will eliminate this match. All other listings used the full model: "Kiss X4"
# b. Do this by creating a special code for x, instead of using 'a' = alpha, when on its own.
# 
#
# --------------------------------------------------------------------------------------
# 10.6.4. The TRYX EX-TR100 matches on TRYX not EX-TR100.
# 
# index_l index_p manufacturer  family  model  productDesc
# 12578       705        Casio  Exilim   TRYX  Casio Exilim TRYX EX-TR100 Digitalkamera (12 Megapixel, dreh-, schwenk und kippbares 7,6 cm (3 Zoll) Display) schwarz
# 12579       705        Casio  Exilim   TRYX  Casio Exilim TRYX EX-TR100 Digitalkamera (12 Megapixel, dreh-, schwenk und kippbares 7,6 cm (3 Zoll) Display) schwarz
# 12593       705        Casio  Exilim   TRYX  Casio Exilim TRYX EX-TR100 Digitalkamera (12 Megapixel, dreh-, schwenk und kippbares 7,6 cm (3 Zoll) Display) weiß
# 
# Answer:  There is no EX-TR100 model. So this is correct.
#
# products[products.model.str.contains('TR-100')][['manufacturer','family','model']]
# products[products.model.str.contains('TR100')][['manufacturer','family','model']]
# products[products.model.str.contains('TR 100')][['manufacturer','family','model']]
# 
# 
# Corrective action:
# a. No need to do anything.
# b. Nice to have: when family+model = 'n+n' or '+n', make the value of the match on "family and model" much lower.
#    Although it doesn't appear to have been an issue with this data set, it might have been a problem with a different data set.
# 
#
# --------------------------------------------------------------------------------------
# 10.6.5. The "Leica Digilux" product matches a variety of different models (different MP ratings)
# 
# index_l index_p manufacturer   family    model  productDesc
# 16021         7        Leica           Digilux  Leica 'Digilux 2' 5MP Digital Camera
# 16022         7        Leica           Digilux  Leica 'Digilux 2' 5MP Digital Camera
# 15984         7        Leica           Digilux  Leica DIGILUX 3 7.5MP Digital SLR Camera
# 15985         7        Leica           Digilux  Leica DIGILUX 3 7.5MP Digital SLR Camera
# 16026         7        Leica           Digilux  Leica Digilux 1 3.9MP Digital Camera
# 
# Corrective action:
# a. Ensure that the code to choose the highest weighted MP rating, 
#    requires a sufficient gap between first and second highest weightings.
#    If a variety of MP ratings are similarly likely, set the MP rating to an invalid number (e.g. -1).
#    This should serve to eliminate all these matches.
# 
# 
# --------------------------------------------------------------------------------------
# 10.6.6. The "Olympus E-100 RS" was matched instead of an "E 30" 
#         because the listing's description contained "Vis�e 100%"
# 
# index_l index_p manufacturer  family     model  productDesc
# 8270    400          Olympus          E-100 RS  Olympus - E 30 - Appareil Photo Numérique Reflex (Boîtier nu) - AF 11points Visée 100% - Écran LCD 2,5" - Stabilisateur mécanique
# 
# Answer: 
# i.  The '�' was presumably not seen as an alpha character, so the regex still matched on the left.
# ii. The '%' is not one of the characters to the right which would cause the regex to fail.
# 
# Corrective action:
# a. Change regex to ensure that the number in a product code is not followed by a percent symbol.
# 
# 
# --------------------------------------------------------------------------------------
# 10.6.7. The "� TOUGH-3000" ended up matching the Stylus instead of the mju
# 
# index_l index_p manufacturer  family       model  productDesc
# 8167    187          Olympus  Stylus  Tough-3000  Olympus - µ TOUGH-3000 - Appareil photo numérique - 12 Mpix - Rose
# 8108    187          Olympus  Stylus  Tough-3000  Olympus - µ TOUGH-3000 - Appareil photo numérique - 12 Mpix - Rouge
# 8109    187          Olympus  Stylus  Tough-3000  Olympus - µ TOUGH-3000 - Appareil photo numérique - 12 Mpix - Rouge
# 8123    187          Olympus  Stylus  Tough-3000  Olympus - µ TOUGH-3000 - Appareil photo numérique - 12 Mpix - Vert
# 8124    187          Olympus  Stylus  Tough-3000  Olympus - µ TOUGH-3000 - Appareil photo numérique - 12 Mpix - Vert
# 7495    187          Olympus  Stylus  Tough-3000  Olympus ? TOUGH-3000 Digital Compact Camera - Hot Pink (12MP, 3.6x wide Optical Zoom) 2.7 inch LCD
# 
# Corrective action:
# a. None. This was a known issue which we decided to live with previously.
# 
# 
# --------------------------------------------------------------------------------------
# 10.6.8. Is the Ricoh GR A12 the same as the GXR (A12)?
# 
# index_l index_p manufacturer  family     model   productDesc
# 16304   204            Ricoh          GXR (A12)  Ricoh - Objectif GR LENS A12 28 mm F2.5
# 16305   204            Ricoh          GXR (A12)  Ricoh - Objectif GR LENS A12 28 mm F2.5
# 16224   204            Ricoh          GXR (A12)  Ricoh A12 GR - Digital camera lens unit - prosumer - 12.3 Mpix
# 
# Answer: No. The GR and GXR are different cameras. The A12 is being used as the product code rather than the GXR.
# 
# Corrective action:
# a. Don't allow product codes to be in brackets; and...
# b. Treat a "+c_" match as being a product code (with a relatively low value).
#    Rely on the 10x rule to make it a higher match than the A12, which comes after a bracket.
#    This will only help if there is a Ricoh GR product to match it to.
#    But then it will create a new correct match, rather than just removing an incorrect match.


# ------------------------------------------------------------------------------------
# Results of fixing the above errors:
# 
# 10.6.1 No corrective action required.
# 
# 10.6.2 To be addressed in section 11 below.
# 
# 10.6.3 Success! 
#        The Kiss X4 is no longer a match for the "Canon - PowerShot E1 - Appareil photo compact num�rique - Capteur 10 MP - Zoom optique x4..."
#        HOWEVER, the price paid is that a correct match is now lost:
#           The Fujifilm FinePix X100 no longer matches listing "Fujifilm X100 12.3 MP APS-C CMOS EXR Digital Camera,23mm Fujinon Lens and 2.8-Inch LCD"
#        Since incorrect matches are more heavily weighted than correct matches, this is an acceptable trade-off.
# 
# 10.6.4 No corrective action required.
# 
# 10.6.5 To be addressed in section 11 below.
# 
# 10.6.6 Checked that the E-100 is no longer matching a listing containing "Vis�e 100%".
# 
# 10.6.7 No corrective action will be taken.
# 
# 10.6.8 Success! The following 3 listings are no longer being matched to the Ricoh GXR (A12):
#        a. Ricoh - Objectif GR LENS A12 28 mm F2.5,,1029999991,Prod code without a dash approximately
#        b. Ricoh - Objectif GR LENS A12 28 mm F2.5,,1029999991,Prod code without a dash approximately
#        c. Ricoh A12 GR - Digital camera lens unit - prosumer - 12.3 Mpix,,1029999991,Prod code without a dash approximately
# 
#        HOWEVER:
#        Should they be matched to the Ricoh GR Digital III product?
#        This could be achieved by treating a '+c_' pattern as a product code with a low value match.
#        This is especially useful if we restrict the 'c' classification to at least 2 characters.
#        But this may open the door to more mismatches, particularly since there are multiple version of the Ricoh GR, but only one in this data set.


# ==============================================================================
# 11. Estimate the Megapixel rating of each product and use this
#     to filter out incorrect matches:
#


# -----------------------------------------------------------------------------
# 11.1 Estimate the likely Megapixel rating of each product
#     based on the Megapixel ratings of the highest valued matches:
# 

CALCULATE_MEGAPIXELS_FROM_BEST_MATCHES_ONLY = True
# This was added to address issue of Powershot SX 130 IS mega-pixel ratings being used for the IXUS 130, 
# leading to rejection of IXUS 130 ratings due to the MP mismatch.
# Originally the code used all product-listing matches, not just the best matches for each listing.

best_matches_grouped_by_product_mp_and_result_value = best_matches[
    best_matches.rounded_MP.notnull()].groupby(['index_p', 'rounded_MP', 'match_result_value'])
best_matches_by_product_mp_and_result_value_with_counts \
    = DataFrame({'group_count' : best_matches_grouped_by_product_mp_and_result_value.size()}).reset_index()

all_matches_grouped_by_product_mp_and_result_value = matched_products_and_listings[
    matched_products_and_listings.rounded_MP.notnull()].groupby(['index_p', 'rounded_MP', 'match_result_value'])
all_matches_by_product_mp_and_result_value_with_counts \
    = DataFrame({'group_count' : all_matches_grouped_by_product_mp_and_result_value.size()}).reset_index()

if CALCULATE_MEGAPIXELS_FROM_BEST_MATCHES_ONLY:
    matches_grouped_by_product_mp_and_result_value = best_matches_grouped_by_product_mp_and_result_value
    matches_by_product_mp_and_result_value_with_counts = best_matches_by_product_mp_and_result_value_with_counts
else:
    matches_grouped_by_product_mp_and_result_value = all_matches_grouped_by_product_mp_and_result_value
    matches_by_product_mp_and_result_value_with_counts = all_matches_by_product_mp_and_result_value_with_counts


THRESHOLD_FOR_REJECTING_MPS_DUE_TO_DIVERSITY = 0.75

def get_rounded_MP_of_best_value_match(grp_by_prod):
    by_val = grp_by_prod.sort_index(by=['match_result_value','group_count'], ascending=False)
    # Check that second best rounded_MP is the same, has lower value, or has significantly lower group_count.
    # Else make rounded_MP -1 to signal too much ambiguity.
    best_rounded_MP = by_val.iloc[0]['rounded_MP']
    if by_val['match_result_value'].count() > 1:
        best_match_result_value = by_val.iloc[0]['match_result_value']
        second_best_rounded_MP = by_val.iloc[1]['rounded_MP']
        second_best_match_result_value = by_val.iloc[1]['match_result_value']
        
        # Check for multiple top-rated mega-pixel ratings:
        if second_best_match_result_value == best_match_result_value:
            count_of_top_valued_MPs = by_val[by_val.match_result_value == best_match_result_value]['group_count'].count()
            if count_of_top_valued_MPs > 2 or abs(second_best_rounded_MP - best_rounded_MP) > 1:
                number_of_top_valued_MPs = by_val[by_val.match_result_value == best_match_result_value]['group_count'].sum()
                best_match_group_count = by_val.iloc[0]['group_count']
                proportion_of_best_match = best_match_group_count / number_of_top_valued_MPs
                if proportion_of_best_match < THRESHOLD_FOR_REJECTING_MPS_DUE_TO_DIVERSITY:
                    return -1
                    # There is too much ambiguity in the Megapixel ratings, suggesting that something is wrong with the product record.
                    # So create an invalid MP rating to ensure that all matches (with MP ratings) are rejected:
    return best_rounded_MP

matches_grouped_by_product = matches_by_product_mp_and_result_value_with_counts.groupby('index_p')
best_rounded_MP_by_product = matches_grouped_by_product.apply(get_rounded_MP_of_best_value_match)
best_rounded_MP_by_product_DF = DataFrame({'best_value_rounded_MP' : best_rounded_MP_by_product}).reset_index()
matched_products_and_listings = pd.merge(matched_products_and_listings, best_rounded_MP_by_product_DF, left_on='index_p', right_on='index_p', how='left')


# -----------------------------------------------------------------------------
# 11.2 Calculate the highest valued product for each listing, 
#      where the listing's rounded megapixel rating matches 
#      the highest valued megapixel rating
#      

def get_is_rounded_MP_matched(matched_prod_and_listing):
    rounded_MP = matched_prod_and_listing['rounded_MP']
    best_value_rounded_MP = matched_prod_and_listing['best_value_rounded_MP']
    return abs(rounded_MP - best_value_rounded_MP) <= 1

are_both_MPS_set = pd.notnull(matched_products_and_listings[['rounded_MP', 'best_value_rounded_MP']]).all(axis=1)
matched_products_and_listings['is_highest_type_of_match'] = matched_products_and_listings.match_result_description == BaseMasterTemplateBuilder.all_of_family_and_model_with_regex_desc
matched_products_and_listings['is_best_value_rounded_MP_matched'] = matched_products_and_listings[are_both_MPS_set].apply(get_is_rounded_MP_matched, axis=1)
matched_products_and_listings.is_best_value_rounded_MP_matched = matched_products_and_listings.is_best_value_rounded_MP_matched.fillna(True)

is_not_filtered_out = matched_products_and_listings[['is_highest_type_of_match', 'is_best_value_rounded_MP_matched']].any(axis = 1)

filtered_matched_products_and_listings = matched_products_and_listings[is_not_filtered_out]
filtered_matches_grouped_by_listing = filtered_matched_products_and_listings.groupby('index_l')
filtered_best_matches = filtered_matches_grouped_by_listing.apply(get_highest_value_product_for_listing)
filtered_best_matches[best_match_columns].sort_index(by=best_match_sort_by).to_csv('../data/intermediate/filtered_best_matches_by_match_result_value.csv', encoding='utf-8')

# Result:  This correctly eliminates the EOS 1-D models that are not Mark IV's.
#          HOWEVER...
# Issues:  1. A few listings have equal highest values, but multiple MP ratings.
#             Investigate why this is so.
#             Decide whether to eliminate all of these listings (set best_value_rounded_MP = -1, say).
#             Or possibly choose the lowest valued MP rating.
#          2. German listings seem to always round the Megapixel rating up.
#             Consider accepting the match if the absolute MP rating difference is <= 1.
#          3. Quite a few listings have errors in the Megapixel rating. But they seem to be correct otherwise.
#             Consider only eliminating lower-valued matches.
#             Alternatively, always keep listings where match_result_description = 'Family and model approximately'
# 
# Actions taken:
# 
# a. Don't filter out listings with MP ratings that are 1 away from the best value MP rating.
# 
#    RESULT: 
#    
#    Many of the excluded listings are now being included again.
# 
# b. Modify get_rounded_MP_of_best_value_match() to set the MP to -1
#    if there are multiple MP ratings at the highest match_result_value
#    and none of these ratings has at least 75% of the matching listings.
# 
#    RESULT:
# 
# The following listings will be excluded due to mismatch:
#    
# index_l,index_p,manufacturer,family,model,productDesc,extraProdDetails,match_result_value,match_result_description
# 12561,254,Casio,Exilim,EX-ZR10,"Casio Exilim EX-ZR10 Highspeed-Digitalkamera (14 Megapixel, 7-fach opt, Zoom, 7,6 cm (3 Zoll) Display, bildstabilisiert) pink",,11399999987,Family and model approximately
# 12562,254,Casio,Exilim,EX-ZR10,"Casio Exilim EX-ZR10 Highspeed-Digitalkamera (14 Megapixel, 7-fach opt, Zoom, 7,6 cm (3 Zoll) Display, bildstabilisiert) pink",,11399999987,Family and model approximately
# 12563,254,Casio,Exilim,EX-ZR10,"Casio Exilim EX-ZR10 Highspeed-Digitalkamera (14 Megapixel, 7-fach opt, Zoom, 7,6 cm (3 Zoll) Display, bildstabilisiert) pink",,11399999987,Family and model approximately
# 14245,641,Fujifilm,FinePix,Z90,Fujifilm - FinePix Z90 - Appareil photo num�rique - 16 Mpix - Rose,,11099999990,Family and model approximately
# 14246,641,Fujifilm,FinePix,Z90,Fujifilm - FinePix Z90 - Appareil photo num�rique - 16 Mpix - Rose,,11099999990,Family and model approximately
# 14247,641,Fujifilm,FinePix,Z90,Fujifilm - FinePix Z90 - Appareil photo num�rique - 16 Mpix - Violet,,11099999990,Family and model approximately
# 14248,641,Fujifilm,FinePix,Z90,Fujifilm - FinePix Z90 - Appareil photo num�rique - 16 Mpix - Violet,,11099999990,Family and model approximately
# 3012,214,Nikon,Coolpix,S620,Nikon COOLPIX S620 Silver 10MP Digital Camera,,11199999989,Family and model approximately
# 6668,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 6669,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 6670,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 6671,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 7003,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 7004,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 7005,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 8329,324,Olympus,,PEN E-PL1,"Olympus - PEN E-PL1 - Appareil Photo Bridge - 12,3 Mpix - Kit bo�tier Champagne",Objectif 14-150 mm Noir,10899999991,Family and model approximately
# 8330,324,Olympus,,PEN E-PL1,"Olympus - PEN E-PL1 - Appareil Photo Bridge - 12,3 Mpix - Kit bo�tier Champagne",Objectif 14-150 mm Noir,10899999991,Family and model approximately
# 8324,324,Olympus,,PEN E-PL1,"Olympus - PEN E-PL1 - Appareil Photo Bridge - 12,3 Mpix - Kit bo�tier Noir",Objectif 14-150mm Noir,10899999991,Family and model approximately
# 8325,324,Olympus,,PEN E-PL1,"Olympus - PEN E-PL1 - Appareil Photo Bridge - 12,3 Mpix - Kit bo�tier Noir",Objectif 14-150mm Noir,10899999991,Family and model approximately
# 8300,324,Olympus,,PEN E-PL1,"Olympus - PEN E-PL1 DZK - Appareil Photo Bridge - 12,3 Mpix - Kit bo�tier Noir",Objectifs 14-42 mm / 40-155 mm Noir,10899999991,Family and model approximately
# 8301,324,Olympus,,PEN E-PL1,"Olympus - PEN E-PL1 DZK - Appareil Photo Bridge - 12,3 Mpix - Kit bo�tier Noir",Objectifs 14-42 mm / 40-155 mm Noir,10899999991,Family and model approximately
# 8336,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Compact � objectifs interchangeables - Bo�tier nu - 12,3 Mpix - Blanc",,10899999991,Family and model approximately
# 8337,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Compact � objectifs interchangeables - Bo�tier nu - 12,3 Mpix - Blanc",,10899999991,Family and model approximately
# 8298,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Compact � objectifs interchangeables - Bo�tier nu - 12,3 Mpix - Champagne",,10899999991,Family and model approximately
# 8299,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Compact � objectifs interchangeables - Bo�tier nu - 12,3 Mpix - Champagne",,10899999991,Family and model approximately
# 8331,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Compact � objectifs interchangeables - Bo�tier nu - 12,3 Mpix - Noir",,10899999991,Family and model approximately
# 8332,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Compact � objectifs interchangeables - Bo�tier nu - 12,3 Mpix - Noir",,10899999991,Family and model approximately
# 8253,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Blanc - 12,3 Mpix",Objectif 14 - 42mm - Argent,10899999991,Family and model approximately
# 8254,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Blanc - 12,3 Mpix",Objectif 14 - 42mm - Argent,10899999991,Family and model approximately
# 8313,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Blanc - 12,3 Mpix",Objectif 14 - 42mm - Argent,10899999991,Family and model approximately
# 8314,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Blanc - 12,3 Mpix",Objectif 14 - 42mm - Argent,10899999991,Family and model approximately
# 8251,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Champagne - 12,3 Mpix",Objectif 14 - 42mm - Argent,10899999991,Family and model approximately
# 8252,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Champagne - 12,3 Mpix",Objectif 14 - 42mm - Argent,10899999991,Family and model approximately
# 8311,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Champagne - 12,3 Mpix",Objectif 14 - 42mm - Argent,10899999991,Family and model approximately
# 8312,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Champagne - 12,3 Mpix",Objectif 14 - 42mm - Argent,10899999991,Family and model approximately
# 8255,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Noir - 12,3 Mpix",Objectif 14 - 42mm - Noir,10899999991,Family and model approximately
# 8256,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Noir - 12,3 Mpix",Objectif 14 - 42mm - Noir,10899999991,Family and model approximately
# 8257,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Noir - 12,3 Mpix",Objectif 14 - 42mm - Noir,10899999991,Family and model approximately
# 8315,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Noir - 12,3 Mpix",Objectif 14 - 42mm - Noir,10899999991,Family and model approximately
# 8316,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Noir - 12,3 Mpix",Objectif 14 - 42mm - Noir,10899999991,Family and model approximately
# 8317,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Noir - 12,3 Mpix",Objectif 14 - 42mm - Noir,10899999991,Family and model approximately
# 8265,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Rouge - 12,3 Mpix",Objectif 14 - 42mm - Noir,10899999991,Family and model approximately
# 8266,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Rouge - 12,3 Mpix",Objectif 14 - 42mm - Noir,10899999991,Family and model approximately
# 8322,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Rouge - 12,3 Mpix",Objectif 14 - 42mm - Noir,10899999991,Family and model approximately
# 8323,324,Olympus,,PEN E-PL1,"Olympus - Pen E-PL1 - Kit compact � objectifs interchangeables - Bo�tier Rouge - 12,3 Mpix",Objectif 14 - 42mm - Noir,10899999991,Family and model approximately
# 6624,324,Olympus,,PEN E-PL1,"Olympus E-PL1 - Digital camera - mirrorless system - 12.3 Mpix - Olympus M.Zuiko Digital 14-42mm and Zuiko Digital 40-150mm lenses - optical zoom: 3 x - supported memory: SD, SDHC - black",,3149999991,Prod code with dash approximately
# 6833,324,Olympus,,PEN E-PL1,"Olympus E-PL1 - Digital camera - mirrorless system - 12.3 Mpix - Olympus M.Zuiko Digital 14-42mm and Zuiko Digital 40-150mm lenses - optical zoom: 3 x - supported memory: SD, SDHC - black",,3149999991,Prod code with dash approximately
# 7284,324,Olympus,,PEN E-PL1,"Olympus E-PL1 - Digital camera - mirrorless system - 12.3 Mpix - Olympus M.Zuiko Digital 14-42mm lens - optical zoom: 3 x - supported memory: SD, SDHC - champagne",,3149999991,Prod code with dash approximately
# 7552,324,Olympus,,PEN E-PL1,Olympus E-PL1 14-42 mm Kit; 12.3 MP; 4032 x 3042 pixels; 2560 x 1920 1024 x 768; 0 x; 0 x; Live MOS (N3839292),,3149999991,Prod code with dash approximately
# 6453,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Black),10899999991,Family and model approximately
# 6454,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Black),10899999991,Family and model approximately
# 6562,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Black),10899999991,Family and model approximately
# 6563,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Black),10899999991,Family and model approximately
# 6564,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Black),10899999991,Family and model approximately
# 6761,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Black),10899999991,Family and model approximately
# 6762,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Black),10899999991,Family and model approximately
# 6763,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Black),10899999991,Family and model approximately
# 6588,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Black) + 8GB Deluxe Accessory Kit,10899999991,Family and model approximately
# 6589,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Black) + 8GB Deluxe Accessory Kit,10899999991,Family and model approximately
# 6700,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,"14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Black) + SSE Best Value 32GB, Deluxe Carrying Case, HDMI Cable, Lens & Tripod Complete Accessories Package",10899999991,Family and model approximately
# 6551,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Blue),10899999991,Family and model approximately
# 6552,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Blue),10899999991,Family and model approximately
# 6698,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,"14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Blue) + SSE Best Value 16GB, Deluxe Carrying Case, HDMI Cable, Lens & Tripod Complete Accessories Package",10899999991,Family and model approximately
# 6699,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,"14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Blue) + SSE Best Value 32GB, Deluxe Carrying Case, Battery, Lens & Tripod Complete Accessories Package",10899999991,Family and model approximately
# 6602,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Champagne Gold) + 8GB Deluxe Accessory Kit,10899999991,Family and model approximately
# 6702,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,"14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Champagne Gold) + SSE Best Value 16GB, Deluxe Carrying Case, Battery, Lens & Tripod Complete Accessories Package",10899999991,Family and model approximately
# 6701,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,"14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Champagne Gold) + SSE Best Value 32GB, Deluxe Carrying Case, Battery, Lens & Flash Complete Accessories Package",10899999991,Family and model approximately
# 6568,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Champagne Silver),10899999991,Family and model approximately
# 6569,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Champagne Silver),10899999991,Family and model approximately
# 6570,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Champagne Silver),10899999991,Family and model approximately
# 6790,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Champagne Silver),10899999991,Family and model approximately
# 6791,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Champagne Silver),10899999991,Family and model approximately
# 6792,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Champagne Silver),10899999991,Family and model approximately
# 6543,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Gold),10899999991,Family and model approximately
# 6544,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Gold),10899999991,Family and model approximately
# 6565,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Slate Blue),10899999991,Family and model approximately
# 6566,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Slate Blue),10899999991,Family and model approximately
# 6567,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Slate Blue),10899999991,Family and model approximately
# 6774,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Slate Blue),10899999991,Family and model approximately
# 6775,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Slate Blue),10899999991,Family and model approximately
# 6776,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Slate Blue),10899999991,Family and model approximately
# 6599,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens (Slate Blue) + 8GB Deluxe Accessory Kit,10899999991,Family and model approximately
# 6594,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,14-42mm f/3.5-5.6 Zuiko Digital Zoom Lens and ED 40-150mm f/4.0-5.6 M.Zuiko Digital Camera Zoom Lens (Black) + 8GB Deluxe Accessory Kit,10899999991,Family and model approximately
# 7147,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,ED 14-150mm f/4.0-5.6 micro Four Thirds Zoom Lens,10899999991,Family and model approximately
# 6595,324,Olympus,,PEN E-PL1,Olympus PEN E-PL1 12.3MP Live MOS Micro Four Thirds Interchangeable Lens Digital Camera,ED 14-150mm f/4.0-5.6 micro Four Thirds Zoom Lens + 8GB Deluxe Accessory Kit,10899999991,Family and model approximately
# 8021,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (12 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) blau",14-42mm Objektiv schwarz,10899999991,Family and model approximately
# 8022,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (12 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) blau",14-42mm Objektiv schwarz,10899999991,Family and model approximately
# 8042,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) Geh�use champagner",,10899999991,Family and model approximately
# 8043,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) Geh�use champagner",,10899999991,Family and model approximately
# 8044,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) Geh�use champagner",,10899999991,Family and model approximately
# 8038,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) Geh�use schwarz",,10899999991,Family and model approximately
# 8039,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) Geh�use schwarz",,10899999991,Family and model approximately
# 8040,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) Geh�use schwarz",,10899999991,Family and model approximately
# 8050,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) Geh�use wei�",,10899999991,Family and model approximately
# 8051,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) Geh�use wei�",,10899999991,Family and model approximately
# 8011,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) champagner",14-150mm Objektiv schwarz,10899999991,Family and model approximately
# 8012,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) champagner",14-150mm Objektiv schwarz,10899999991,Family and model approximately
# 8033,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) champagner",14-42mm & 40-150mm Objektiven silber,10899999991,Family and model approximately
# 8034,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) champagner",14-42mm & 40-150mm Objektiven silber,10899999991,Family and model approximately
# 8019,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) champagner",14-42mm Objektiv silber,10899999991,Family and model approximately
# 8020,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) champagner",14-42mm Objektiv silber,10899999991,Family and model approximately
# 8031,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) rot",14-42mm Objektiv schwarz,10899999991,Family and model approximately
# 8032,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) rot",14-42mm Objektiv schwarz,10899999991,Family and model approximately
# 8013,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) schwarz",14-150mm Objektiv schwarz,10899999991,Family and model approximately
# 8014,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) schwarz",14-150mm Objektiv schwarz,10899999991,Family and model approximately
# 8015,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) schwarz",14-150mm Objektiv schwarz,10899999991,Family and model approximately
# 8023,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) schwarz",14-42mm & 40-150mm Objektiven schwarz,10899999991,Family and model approximately
# 8024,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) schwarz",14-42mm & 40-150mm Objektiven schwarz,10899999991,Family and model approximately
# 8025,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) schwarz",14-42mm & 40-150mm Objektiven schwarz,10899999991,Family and model approximately
# 7998,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) schwarz",14-42mm Objektiv schwarz,10899999991,Family and model approximately
# 7999,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) schwarz",14-42mm Objektiv schwarz,10899999991,Family and model approximately
# 8000,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) schwarz",14-42mm Objektiv schwarz,10899999991,Family and model approximately
# 8026,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) wei�",14-42mm & 40-150mm Objektiven silber,10899999991,Family and model approximately
# 8006,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) wei�",14-42mm Objektiv silber,10899999991,Family and model approximately
# 8007,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm (2,7 Zoll) Display, Bildstabilisator) wei�",14-42mm Objektiv silber,10899999991,Family and model approximately
# 8035,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm Display, Bildstabilisator) Double Zoom Kit (EZ-M1442L & EZ4015-2) champagner",,10899999991,Family and model approximately
# 8029,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm Display, Bildstabilisator) Double Zoom Kit (EZ-M1442L & EZ4015-2) schwarz",,10899999991,Family and model approximately
# 8030,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm Display, Bildstabilisator) Double Zoom Kit (EZ-M1442L & EZ4015-2) schwarz",,10899999991,Family and model approximately
# 8027,324,Olympus,,PEN E-PL1,"Olympus PEN E-PL1 Systemkamera (13 Megapixel, 6,9 cm Display, Bildstabilisator) Double Zoom Kit (EZ-M1442L & EZ4015-2) wei�",,10899999991,Family and model approximately
# 16133,246,Ricoh,,CX2,Ricoh CX2 9.29MP Digital Camera,10.7x Optical Image Stabilized Zoom and 3 inch High Resolution LCD (Black),10299999997,Family and model approximately
# 16128,246,Ricoh,,CX2,Ricoh CX2 9.29MP Digital Camera,10.7x Optical Image Stabilized Zoom and 3 inch High Resolution LCD (Silver),10299999997,Family and model approximately
# 16129,246,Ricoh,,CX2,Ricoh CX2 9.29MP Digital Camera,10.7x Optical Image Stabilized Zoom and 3 inch High Resolution LCD (Silver),10299999997,Family and model approximately
# 19505,246,Ricoh,,CX2,"Ricoh CX2 Digitalkamera (10 Megapixel, 10-fach opt. Zoom, 7,6 cm (3 Zoll) Display, Bildstabilisator) grau/pink",,10299999997,Family and model approximately
# 19506,246,Ricoh,,CX2,"Ricoh CX2 Digitalkamera (10 Megapixel, 10-fach opt. Zoom, 7,6 cm (3 Zoll) Display, Bildstabilisator) grau/pink",,10299999997,Family and model approximately
# 19507,246,Ricoh,,CX2,"Ricoh CX2 Digitalkamera (10 Megapixel, 10-fach opt. Zoom, 7,6 cm (3 Zoll) Display, Bildstabilisator) grau/pink",,10299999997,Family and model approximately
# 19493,246,Ricoh,,CX2,"Ricoh CX2 Digitalkamera (10 Megapixel, 10-fach opt. Zoom, 7,6 cm (3 Zoll) Display, Bildstabilisator) schwarz",,10299999997,Family and model approximately
# 19494,246,Ricoh,,CX2,"Ricoh CX2 Digitalkamera (10 Megapixel, 10-fach opt. Zoom, 7,6 cm (3 Zoll) Display, Bildstabilisator) schwarz",,10299999997,Family and model approximately
# 19511,246,Ricoh,,CX2,"Ricoh CX2 Digitalkamera (10 Megapixel, 10-fach opt. Zoom, 7,6 cm (3 Zoll) Display, Bildstabilisator) silber",,10299999997,Family and model approximately
# 19512,246,Ricoh,,CX2,"Ricoh CX2 Digitalkamera (10 Megapixel, 10-fach opt. Zoom, 7,6 cm (3 Zoll) Display, Bildstabilisator) silber",,10299999997,Family and model approximately
# 891,703,Samsung,,WB700,"Samsung - WB700 - Appareil photo num�rique - 16,4 Mpix - Noir",,10499999995,Family and model approximately
# 
# The following listings are also being excluded now, arguably correctly:
# 
# index_l,index_p,manufacturer,family,model,productDesc,extraProdDetails,match_result_value,match_result_description
# 16021,7,Leica,,Digilux,Leica 'Digilux 2' 5MP Digital Camera,3.2x Optical Zoom,10699999993,Family and model approximately
# 16022,7,Leica,,Digilux,Leica 'Digilux 2' 5MP Digital Camera,3.2x Optical Zoom,10699999993,Family and model approximately
# 15984,7,Leica,,Digilux,Leica DIGILUX 3 7.5MP Digital SLR Camera,Leica D 14-50mm f/2.8-3.5 ASPH Lens with Optical Image Stabilization,10699999993,Family and model approximately
# 15985,7,Leica,,Digilux,Leica DIGILUX 3 7.5MP Digital SLR Camera,Leica D 14-50mm f/2.8-3.5 ASPH Lens with Optical Image Stabilization,10699999993,Family and model approximately
# 16026,7,Leica,,Digilux,Leica Digilux 1 3.9MP Digital Camera,3x Optical Zoom,10699999993,Family and model approximately
#    
# INVESTIGATIONS:
# 
# a. Why are so many PEN E-PL1 listings being rejected?
# 
# matches_by_product_mp_and_result_value_with_counts[matches_by_product_mp_and_result_value_with_counts.index_p == 324]
# 
#      index_p  rounded_MP  match_result_value  group_count
# 327      324          12          3149999991            4
# 328      324          12          3252999982            7
# 329      324          12         10899999991           68
# 330      324          13         10899999991           32
#
# ANSWER: Because 68% have an MP rating of 12, and 32% have MP rating of 13 (German listings), so the threshold of 75% has not been achieved.
#
# b. Why are the Ricoh CX2 listings being rejected?
# 
# ANSWER: 70% of the listings are at 10 Megapixels (German listings) and the other 30% at 9 MP. The threshold of 75% has not been achieved.
#
# CONCLUSION: 
# 
# The majority of the rejected listings appear to be due to:
# 
# i. German listings where the Megapixels have been rounded up, or
# ii. Typos
# 
# It doesn't make sense to eliminate 131 good matches in order to eliminate the 5 suspect matches for the Digilux product.
# The problem with the Digilux product is that it is insufficiently precise ("Digilux" is arguably the family not the model).
# 
# This can be fixed through 2 changes:
# 
# a. Modify the matching rule for "Family and model approximately" to either:
#    i.  require a digit or dash in the combined family and model, or
#    ii. reject models whose classification pattern is just 'a'
# 
# b. Ignore the Megapixel filtering rule for matches where the match_result_description is 'Family and model approximately'.
# 

# Outcome:
#
# a. [Reject models whose classification pattern is just 'a']
# 
#    RESULT:  The Digilux model is no longer matched in the pre-filtered best_matches_by_match_result_value.csv
#    HOWEVER: Neither are the Casio Exilim TRYX, Kodak Slice.
#    SO:      Add back the rule for 'a' models, but with a very low priority.
#    RESULT:  Now the three products with 'a' models are back, 
#             but with description: "Family and alpha model approximately"
# 
# b. Ignore the Megapixel filtering rule for 'Family and model approximately' listings
#    
#    RESULTS: a. The EOS 1-D models which aren't Mark IV's are correctly filtered out.
#             b. The Digilux models are correctly filtered out now.
#             c. The following models are incorrectly filtered out:
# 
# index_l,index_p,manufacturer,family,model,productDesc,extraProdDetails,match_result_value,match_result_description
# 6668,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 6669,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 6670,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 6671,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 7003,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 7004,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 7005,324,Olympus,,PEN E-PL1,OLYMPUS 262855 12.3 Megapixel E-PL1 Pen Camera (Black camera body),,3252999982,Prod code with dash approximately
# 6624,324,Olympus,,PEN E-PL1,"Olympus E-PL1 - Digital camera - mirrorless system - 12.3 Mpix - Olympus M.Zuiko Digital 14-42mm and Zuiko Digital 40-150mm lenses - optical zoom: 3 x - supported memory: SD, SDHC - black",,3149999991,Prod code with dash approximately
# 6833,324,Olympus,,PEN E-PL1,"Olympus E-PL1 - Digital camera - mirrorless system - 12.3 Mpix - Olympus M.Zuiko Digital 14-42mm and Zuiko Digital 40-150mm lenses - optical zoom: 3 x - supported memory: SD, SDHC - black",,3149999991,Prod code with dash approximately
# 7284,324,Olympus,,PEN E-PL1,"Olympus E-PL1 - Digital camera - mirrorless system - 12.3 Mpix - Olympus M.Zuiko Digital 14-42mm lens - optical zoom: 3 x - supported memory: SD, SDHC - champagne",,3149999991,Prod code with dash approximately
# 7552,324,Olympus,,PEN E-PL1,Olympus E-PL1 14-42 mm Kit; 12.3 MP; 4032 x 3042 pixels; 2560 x 1920 1024 x 768; 0 x; 0 x; Live MOS (N3839292),,3149999991,Prod code with dash approximately
#
#    WHY:     Because less than 75% of the highest valued matches have the same megapixel rating, leading to a fake rating of -1 MP.
#             And the match value description for these records is "Prod code with dash approximately"
#    SO:      Use a threshold match value instead, such as BaseMasterTemplateBuilder.prod_code_having_no_dash_with_regex_value_func_on_prod_desc
#             This will include all product code matches, but exclude the family+model matches where model is alpha only. 
#    BUT:     This would make the older EOS 1-D models match the Mark IV again.
#    SO:      Accept that the price of fixing the EOS 1-D mismatches is that these 11 PEN E-PL1 listings won't get matched.
#    BUT:     The PEN E-PL1 only has 2 MP ratings (12 MP and 13 MP, caused by the German listings rounding up not down).
#             So why is it being set to -1 MP?
#    ANSWER:  There was a bug, which has now been fixed!
#    RESULT:  The Pen E-PL1 listings are now being correctly matched again.
#             Only the EOS 1-D's and the Leica Digilux are being filtered out now!



# ==============================================================================
# 12. Analyze listings which weren't matched to any product:
#

# -----------------------------------------------------------------------------
# 12.1 Set matched product on all listings:
# 

filtered_columns = ['index_p', 'index_l']
filtered_prod_columns = ['family', 'model', 'manufacturer', 'product_name', 'announced-date']
listings_with_matched_products = pd.merge( listingsByPManuf, filtered_best_matches[filtered_columns], how='left', left_index=True, right_on='index_l')
listings_with_matched_products = pd.merge( 
    listings_with_matched_products, products[filtered_prod_columns], how='left', left_on='index_p', right_index=True )

# listings_with_matched_products.head()


# -----------------------------------------------------------------------------
# 12.2 Find all listings which haven't been matched to a product:
# 

unmatched_listings_cols = ['pManuf', 'productDesc', 'extraProdDetails']
unmatched_listings = listings_with_matched_products[listings_with_matched_products.index_p.isnull()][unmatched_listings_cols]
unmatched_listings.sort_index(by=unmatched_listings_cols).to_csv('../data/intermediate/unmatched_listings.csv', encoding='utf-8')


# search_string = '733'
# products[products.model.str.contains(search_string)][['manufacturer', 'family', 'model']].head()
# products[products.model.str.contains(search_string)].model.count()
#
# Filter by manufacturer:
# products[products.manufacturer.str.contains('Agfa')][['manufacturer', 'family', 'model']].head()


# ISSUES DISCOVERED:
# 
# -----------------------------------------------------------------------------
# ISSUE 1:
# 
# Some listings have product codes with a character appended to indicate the colour of the product.
# Others have the words HD or IS appended to the code.
# These suffixes cause the product code matches to fail.
# 
# CORRECTIVE ACTION:
#    
# a. Add a low value product code regex which checks that the product code
#    is followed by a single letter or specific letters (i.e. HD or IS).
#    
# RESULT:
# 
# Many new (correct) matches now found:
# 
# 5x Canon PowerShot A2200IS
# 1x Canon PowerShot S90IS
# 4x Canon SX30IS
# 4x FUJIFILM FinePix S2950HD
# 4x Fujifilm - FinePix S3300HD
# 9x FUJIFILM FinePix S3400HD
# 1x HP c200A
# 4x Panasonic DMC-F2K
# 3x Panasonic Lumix DMC-F3K
# 2x Panasonic Lumix DMC-FH20K
# 7x Panasonic DMC-FH25* (*=A/K/R/S/V)
# 1x Panasonic DMC-FX48K
# 5x Panasonic DMC-FX75*
# 27x Panasonic - Lumix G - DMC-G2*
# 11x Panasonic DMC-GH1*
# 1x Panasonic Lumix DMC-ZS3*
# 3x Sony - DSLR-A230*
# 15x Sony DSLR A290* SLR
# 1x Sony - DSLR-A330*
# 4x Sony - DSLR-A380*
# 7x Sony DSLR DSLR-A390*
# 7x Sony - DSLR-A450*
# 11x Sony - DSLR-A500*
# 6x Sony - DSLR-A550*
# 6x Sony DSLRA580*
# 6x Sony - DSLR-A850*
# 50x SONY Alpha NEX-3*
# 51x SONY Alpha NEX-5*
# 9x Sony DSC-H55*
# 6x Sony DSC-HX5V*
# 22x Sony - DSC-HX7V*
# 9x Sony DSC-S2000*
# 3x Sony Cyber-shot DSCS950*
# 9x Sony - Cyber-Shot - DSC-T90*
# 7x Sony - Cyber-Shot - DSC-T900
# 30x Sony - Cybershot DSC-T99*
# 13x Sony - CyberShot - DSC-TX1*
# 9x Sony DSC-TX100V*
# 17x Sony DSC-TX5*
# 9x Sony DSC-TX7*
# 17x Sony - Cybershot DSC-TX9*
# 2x Sony Cyber-shot DSC-W180*
# 1x Sony - Cyber-Shot - DSC-W220*
# 2x Sony - Cyber-Shot - DSC-W290*
# 7x Sony DSC-W310*
# 12x Sony DSC-W320*
# 26x Sony DSC-W350*
# 15x Sony DSC-W380*
# 9x Sony - DSC-WX1*
# 26x Sony - Cybershot DSC-WX5*
# 31x Sony - DSC-W530*
# 20x Sony - DSC-H70*
# 11x Sony - DSC-TX10*
# 24x Sony - DSC-W510*
# 1x Sony DSC-W560*
# 25x Sony - DSC-T110*
# 33x Sony - DSC-W570*
# 8x Sony DSC-WX10*
# 22x Sony - DSC-WX7*
# 29x SONY Alpha SLT-A33*
# 33x SONY Alpha SLT-A55*
# 
# Unknown whether this is correct or not:
#
# 6x Pentax - Optio E70L
#    
# NEW ISSUES CREATED:
#
# a. The EOS 1Ds matches the EOS-1D, despite being a different "Mark". Also the 1Ds is not the same as the 1D.
#    
# index_l,index_p,manufacturer,family,model,productDesc,extraProdDetails,match_result_value,match_result_description
# 4183,624,Canon,,EOS-1D Mark IV,Canon EOS 1Ds Mark II 16.7MP Digital SLR Camera (Body Only),,105059972,Prod code excluding last character or IS
# 4184,624,Canon,,EOS-1D Mark IV,Canon EOS 1Ds Mark II 16.7MP Digital SLR Camera (Body Only),,105059972,Prod code excluding last character or IS
# 5326,624,Canon,,EOS-1D Mark IV,Canon EOS 1Ds Mark III Digital SLR Camera (Body Only),,105059972,Prod code excluding last character or IS
# 5327,624,Canon,,EOS-1D Mark IV,Canon EOS 1Ds Mark III Digital SLR Camera (Body Only),,105059972,Prod code excluding last character or IS
# 5328,624,Canon,,EOS-1D Mark IV,Canon EOS 1Ds Mark III Digital SLR Camera (Body Only),,105059972,Prod code excluding last character or IS
# 
# CORRECTIVE ACTION:
# 
# a. Given the large number of correct matches generated, we might just have to live with these 5 errors.
# b. Alternatively, add logic to ensure that Mark XXX matches, as this will also eliminate these matches.
# c. Or add a specific rule to exclude the Canon EOS 1Ds.
# 
# RESULT:
# 
# Issue resolved by specifically excluding the EOS 1-Ds in the regular expression for a product code + extra character.
# 
# -----------------------------------------------------------------------------
# ISSUE 2:
# 
# Some listings are being missed because the product code is a word followed by a number.
# In many cases, the word is the last word in the family, and the number is the first part of the model.
# 
# CORRECTIVE ACTION:
#    
# a. Add a low value rule template based on an 'a+n' pattern, where the 'a' and 'n' must be 
#    at the boundaries of the classification, or next to an underscore (i.e. whitespace).
#    
# RESULT:
# 
# 36 new matches found:
# 
# index_l,index_p,manufacturer,family,model,productDesc,extraProdDetails,match_result_value,match_result_description
# 5771,6,Canon,Digital IXUS,130 IS,CANON Digital Ixus 130 - silver,4 GB SDHC Memory Card (ComboKit),11779964,Word and number crossing family and model
# 6157,258,Canon,Digital IXUS,210 IS,"Canon - IXUS 210 - Appareil photo num�rique - 14,1 Mpix - Tactile - Argent",,1079982,Word and number crossing family and model
# 6174,258,Canon,Digital IXUS,210 IS,"Canon - IXUS 210 - Appareil photo num�rique - 14,1 Mpix - Tactile - Dor�",,1079982,Word and number crossing family and model
# 6175,258,Canon,Digital IXUS,210 IS,"Canon - IXUS 210 - Appareil photo num�rique - 14,1 Mpix - Tactile - Dor�",,1079982,Word and number crossing family and model
# 6091,258,Canon,Digital IXUS,210 IS,"Canon - IXUS 210 - Appareil photo num�rique - 14,1 Mpix - Tactile - Noir",,1079982,Word and number crossing family and model
# 6092,258,Canon,Digital IXUS,210 IS,"Canon - IXUS 210 - Appareil photo num�rique - 14,1 Mpix - Tactile - Noir",,1079982,Word and number crossing family and model
# 6093,258,Canon,Digital IXUS,210 IS,"Canon - IXUS 210 - Appareil photo num�rique - 14,1 Mpix - Tactile - Noir",,1079982,Word and number crossing family and model
# 6131,258,Canon,Digital IXUS,210 IS,"Canon - IXUS 210 - Appareil photo num�rique - 14,1 Mpix - Tactile - Rose",,1079982,Word and number crossing family and model
# 6132,258,Canon,Digital IXUS,210 IS,"Canon - IXUS 210 - Appareil photo num�rique - 14,1 Mpix - Tactile - Rose",,1079982,Word and number crossing family and model
# 6212,258,Canon,Digital IXUS,210 IS,"Canon - IXUS 210 - Appareil photo num�rique - compact - 14.1 Mpix - zoom optique : 5 x - m�moire prise en charge : MMC, SD, SDXC, SDHC, MMCplus - argent�(e)",,1079982,Word and number crossing family and model
# 5467,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digital Camera - Black (14.1 MP, 5x Optical Zoom) 3.5 Inch PureColor Touch LCD",,11779964,Word and number crossing family and model
# 5468,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digital Camera - Black (14.1 MP, 5x Optical Zoom) 3.5 Inch PureColor Touch LCD",,11779964,Word and number crossing family and model
# 5506,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digital Camera - Gold (14.1 MP, 5x Optical Zoom) 3.5 Inch PureColor Touch LCD",,11779964,Word and number crossing family and model
# 5464,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digital Camera - Pink (14.1 MP, 5x Optical Zoom) 3.5 Inch PureColor Touch LCD",,11779964,Word and number crossing family and model
# 5465,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digital Camera - Pink (14.1 MP, 5x Optical Zoom) 3.5 Inch PureColor Touch LCD",,11779964,Word and number crossing family and model
# 5476,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digital Camera - Silver (14.1 MP, 5x Optical Zoom) 3.5 Inch PureColor Touch LCD",,11779964,Word and number crossing family and model
# 5477,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digital Camera - Silver (14.1 MP, 5x Optical Zoom) 3.5 Inch PureColor Touch LCD",,11779964,Word and number crossing family and model
# 5478,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digital Camera - Silver (14.1 MP, 5x Optical Zoom) 3.5 Inch PureColor Touch LCD",,11779964,Word and number crossing family and model
# 5649,258,Canon,Digital IXUS,210 IS,Canon IXUS 210 Digital Camera 14.1MP (Silver) (4196B015),,11779964,Word and number crossing family and model
# 5904,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digitalkamera (14 Megapixel, 5-fach opt. Zoom, 8.9 cm (3.5 Zoll) Full-Touchscreen, bildstabilisiert) gold",,1079982,Word and number crossing family and model
# 5905,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digitalkamera (14 Megapixel, 5-fach opt. Zoom, 8.9 cm (3.5 Zoll) Full-Touchscreen, bildstabilisiert) gold",,1079982,Word and number crossing family and model
# 5906,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digitalkamera (14 Megapixel, 5-fach opt. Zoom, 8.9 cm (3.5 Zoll) Full-Touchscreen, bildstabilisiert) gold",,1079982,Word and number crossing family and model
# 5871,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digitalkamera (14 Megapixel, 5-fach opt. Zoom, 8.9 cm (3.5 Zoll) Full-Touchscreen, bildstabilisiert) pink",,1079982,Word and number crossing family and model
# 5872,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digitalkamera (14 Megapixel, 5-fach opt. Zoom, 8.9 cm (3.5 Zoll) Full-Touchscreen, bildstabilisiert) pink",,1079982,Word and number crossing family and model
# 5873,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digitalkamera (14 Megapixel, 5-fach opt. Zoom, 8.9 cm (3.5 Zoll) Full-Touchscreen, bildstabilisiert) pink",,1079982,Word and number crossing family and model
# 5890,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digitalkamera (14 Megapixel, 5-fach opt. Zoom, 8.9 cm (3.5 Zoll) Full-Touchscreen, bildstabilisiert) schwarz",,1079982,Word and number crossing family and model
# 5891,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digitalkamera (14 Megapixel, 5-fach opt. Zoom, 8.9 cm (3.5 Zoll) Full-Touchscreen, bildstabilisiert) schwarz",,1079982,Word and number crossing family and model
# 5892,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digitalkamera (14 Megapixel, 5-fach opt. Zoom, 8.9 cm (3.5 Zoll) Full-Touchscreen, bildstabilisiert) schwarz",,1079982,Word and number crossing family and model
# 5913,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digitalkamera (14 Megapixel, 5-fach opt. Zoom, 8.9 cm (3.5 Zoll) Full-Touchscreen, bildstabilisiert) silber",,1079982,Word and number crossing family and model
# 5914,258,Canon,Digital IXUS,210 IS,"Canon IXUS 210 Digitalkamera (14 Megapixel, 5-fach opt. Zoom, 8.9 cm (3.5 Zoll) Full-Touchscreen, bildstabilisiert) silber",,1079982,Word and number crossing family and model
# 6218,628,Canon,IXUS,115 HS,IXUS 115,"Hama 60H + 2GB SD + Tripod (Gris, 12MP, Zoom optique 4x, LCD 7,6cm)",1079990,Word and number crossing family and model
# 16617,479,Fujifilm,FinePix,1400 Zoom,Fujifilm FinePix 1400 1.2MP Digital Camera,3x Optical Zoom,2159968,Word and number crossing family and model
# 16623,90,Fujifilm,FinePix,2400 Zoom,Fujifilm FinePix 2400 2MP Digital Camera,3x Optical Zoom,2159968,Word and number crossing family and model
# 16624,90,Fujifilm,FinePix,2400 Zoom,Fujifilm FinePix 2400 2MP Digital Camera,3x Optical Zoom,2159968,Word and number crossing family and model
# 16626,46,Fujifilm,FinePix,4700 Zoom,Fujifilm FinePix 4700 2.4MP  Digital Camera,3x Optical Zoom,2159968,Word and number crossing family and model
# 16636,84,Fujifilm,FinePix,4900 Zoom,Fujifilm FinePix 4900 4.3MP Digital Camera,6x Optical Zoom,2159968,Word and number crossing family and model
# 
# HOWEVER: A lot more IXUS 130 listings were filtered out based on the Megapixels. Why?
# 
# matches_by_product_mp_and_result_value_with_counts[matches_by_product_mp_and_result_value_with_counts.index_p == 6]
# 
#     index_p  rounded_MP  match_result_value  group_count
# 8         6          12          2649999982            4
# 9         6          14             1079982           18
# 10        6          14            11779964            8
# 
#
# Useful script: 
# matched_products_and_listings[matched_products_and_listings.index_p = 6]
# 
# 
# REASON: 
# 
# a. Because the highest match values are used to infer the Megapixel rating, and this happens to be wrong.
# b. These highest match values are for the following camera: "Canon PowerShot SX 130 IS".
#    The matching rule was "model and words in family", so these 4 listings match the model ("130 IS") even though the family is wrong.
# c. And the code to calculate the most likely model is using all possible matches (based on the matching rules) 
#    between listings and products, not the BEST candidate match found for a listing.
# 
# CORRECTIVE ACTION:
# 
# a. See whether the results are better if the best candidate matches are used, instead of all matches.
#    
# RESULT: 
#
# The 26 matches which were previously rejected are now included. And no other matches were affected.
# 
# index_l,index_p,manufacturer,family,model,productDesc,extraProdDetails,match_result_value,match_result_description
# 6096,6,Canon,Digital IXUS,130 IS,"Canon - IXUS 130 - Appareil photo num�rique - 14,1 Mpix - Gris Argent",,1079982,Word and number crossing family and model
# 6097,6,Canon,Digital IXUS,130 IS,"Canon - IXUS 130 - Appareil photo num�rique - 14,1 Mpix - Gris Argent",,1079982,Word and number crossing family and model
# 6105,6,Canon,Digital IXUS,130 IS,"Canon - IXUS 130 - Appareil photo num�rique - 14,1 Mpix - Noir",,1079982,Word and number crossing family and model
# 6106,6,Canon,Digital IXUS,130 IS,"Canon - IXUS 130 - Appareil photo num�rique - 14,1 Mpix - Noir",,1079982,Word and number crossing family and model
# 6109,6,Canon,Digital IXUS,130 IS,"Canon - IXUS 130 - Appareil photo num�rique - 14,1 Mpix - Orange",,1079982,Word and number crossing family and model
# 6110,6,Canon,Digital IXUS,130 IS,"Canon - IXUS 130 - Appareil photo num�rique - 14,1 Mpix - Orange",,1079982,Word and number crossing family and model
# 6153,6,Canon,Digital IXUS,130 IS,"Canon - IXUS 130 - Appareil photo num�rique - 14,1 Mpix - Rose",,1079982,Word and number crossing family and model
# 6154,6,Canon,Digital IXUS,130 IS,"Canon - IXUS 130 - Appareil photo num�rique - 14,1 Mpix - Rose",,1079982,Word and number crossing family and model
# 6201,6,Canon,Digital IXUS,130 IS,"Canon - IXUS 130 - Appareil photo num�rique - compact - 14.1 Mpix - zoom optique : 4 x - m�moire prise en charge : MMC, SD, SDXC, SDHC, MMCplus - argent�(e)",,1079982,Word and number crossing family and model
# 6257,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 - Appareil photo num�rique - compact - 14.1 Mpix - zoom optique : 4 x - m�moire prise en charge : MMC, SD, SDXC, SDHC, MMCplus - noir",,1079982,Word and number crossing family and model
# 5420,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digital Camera - Black (14.1 MP, 4x Optical Zoom) 2.7 Inch PureColor LCD",,11779964,Word and number crossing family and model
# 5421,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digital Camera - Black (14.1 MP, 4x Optical Zoom) 2.7 Inch PureColor LCD",,11779964,Word and number crossing family and model
# 5422,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digital Camera - Black (14.1 MP, 4x Optical Zoom) 2.7 Inch PureColor LCD",,11779964,Word and number crossing family and model
# 5490,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digital Camera - Orange (14.1 MP, 4x Optical Zoom) 2.7 Inch PureColor LCD",,11779964,Word and number crossing family and model
# 5491,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digital Camera - Orange (14.1 MP, 4x Optical Zoom) 2.7 Inch PureColor LCD",,11779964,Word and number crossing family and model
# 5492,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digital Camera - Pink (14.1 MP, 4x Optical Zoom) 2.7 Inch PureColor LCD",,11779964,Word and number crossing family and model
# 5493,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digital Camera - Pink (14.1 MP, 4x Optical Zoom) 2.7 Inch PureColor LCD",,11779964,Word and number crossing family and model
# 5499,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digital Camera - Silver (14.1 MP, 4x Optical Zoom) 2.7 Inch PureColor LCD",,11779964,Word and number crossing family and model
# 5844,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digitalkamera (14 Megapixel, 4-fach opt. Zoom, 6.9 cm (2.7 Zoll) Display, HD Video, bildstabilisiert) orange",,1079982,Word and number crossing family and model
# 5845,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digitalkamera (14 Megapixel, 4-fach opt. Zoom, 6.9 cm (2.7 Zoll) Display, HD Video, bildstabilisiert) orange",,1079982,Word and number crossing family and model
# 5888,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digitalkamera (14 Megapixel, 4-fach opt. Zoom, 6.9 cm (2.7 Zoll) Display, HD Video, bildstabilisiert) pink",,1079982,Word and number crossing family and model
# 5889,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digitalkamera (14 Megapixel, 4-fach opt. Zoom, 6.9 cm (2.7 Zoll) Display, HD Video, bildstabilisiert) pink",,1079982,Word and number crossing family and model
# 5848,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digitalkamera (14 Megapixel, 4-fach opt. Zoom, 6.9 cm (2.7 Zoll) Display, HD Video, bildstabilisiert) schwarz",,1079982,Word and number crossing family and model
# 5849,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digitalkamera (14 Megapixel, 4-fach opt. Zoom, 6.9 cm (2.7 Zoll) Display, HD Video, bildstabilisiert) schwarz",,1079982,Word and number crossing family and model
# 5823,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digitalkamera (14 Megapixel, 4-fach opt. Zoom, 6.9 cm (2.7 Zoll) Display, HD Video, bildstabilisiert) silber",,1079982,Word and number crossing family and model
# 5824,6,Canon,Digital IXUS,130 IS,"Canon IXUS 130 Digitalkamera (14 Megapixel, 4-fach opt. Zoom, 6.9 cm (2.7 Zoll) Display, HD Video, bildstabilisiert) silber",,1079982,Word and number crossing family and model
# 
# -----------------------------------------------------------------------------
# ISSUE 3:
# 
# The previous issue looked at product codes which had the "..._a+n_..." classification pattern.
# See whether there is value in building a rule for "...+a_n_..." patterns.
# 
# INVESTIGATION:
# 
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# a. Classification: a+a_n_a
# 
# Products:
#   manufacturer    family  model
#   Konica Minolta	DiMAGE	EX 1500 Zoom
#   Konica Minolta	DiMAGE	EX 1500 Wide
# 
# Unmatched listings:
#
# index_l,pManuf,productDesc,extraProdDetails
# 20195,Konica Minolta,Minolta Dimage 1500 1.5MP Digital Camera,3x Optical Zoom
# 
# Analysis:
#
# There is only one unmatched listing. It won't match a product code of "EX 1500". 
# And the only clue to distinguish the two products is the "3x Optical Zoom" in the extra product details column.
# 
# Conclusion:
# 
# It is not worth creating a new rule based on the "...+a_n_..." pattern.
# 
# -----------------------------------------------------------------------------
# ISSUE 4:
# 
# Some product codes have neither dashes nor numerics.
# They can be identified by containing only consonants.
# See if there is enough value to trying to match these products too.
# 
# INVESTIGATION:
# 
# Classifications with consonant patterns...
# 
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# a. Classification: +c(an)
# 
# Products:
#   manufacturer  family  model
#   Rico                  GXR (A12)
# 
# Unmatched listings:
#
# index_l,pManuf,productDesc,extraProdDetails
# 20195,Ricoh,Ricoh - GXR - Appareil photo num�rique compact � unit�s interchangeables - 10 Mpix - Bo�tier nu,unit� P10 28-300 mm
# 20195,Ricoh,Ricoh - GXR - Appareil photo num�rique compact � unit�s interchangeables - 10 Mpix - Bo�tier nu,unit� P10 28-300 mm
# 20195,Ricoh,Ricoh - GXR - Appareil photo num�rique compact � unit�s interchangeables - 10 Mpix - Bo�tier nu,unit� P10 28-300 mm
# 20195,Ricoh,Ricoh - GXR - Appareil photo num�rique compact � unit�s interchangeables - 10 Mpix - Bo�tier nu,unit� P10 28-300 mm
# 20195,Ricoh,"Ricoh - GXR - Appareil photo num�rique compact � unit�s interchangeables - 9,2 Mpix - Bo�tier nu",
# 20195,Ricoh,"Ricoh - GXR - Appareil photo num�rique compact � unit�s interchangeables - 9,2 Mpix - Bo�tier nu",
# 20195,Ricoh,"Ricoh - GXR - Appareil photo num�rique compact � unit�s interchangeables - 9,2 Mpix - Bo�tier nu",
# 20195,Ricoh,Ricoh GXR Interchangeable Unit Body,"Ricoh LENS A12 28mm F2.5 Camera Unit, 12 Megapixel"
# 20195,Ricoh,Ricoh GXR Interchangeable Unit Digital Camera System,3-Inch High-Resolution LCD
# 20195,Ricoh,Ricoh GXR Interchangeable Unit Digital Camera System,3-Inch High-Resolution LCD
# 20195,Ricoh,Ricoh GXR Interchangeable Unit Digital Camera System,3-Inch High-Resolution LCD
# 20195,Ricoh,Ricoh GXR Interchangeable Unit Digital Camera System,3-Inch High-Resolution LCD and P10 28-300mm f/3.5-5.6 VC Lens with 10MP CMOS Sensor
# 20195,Ricoh,Ricoh GXR Interchangeable Unit Digital Camera System,3-Inch High-Resolution LCD and P10 28-300mm f/3.5-5.6 VC Lens with 10MP CMOS Sensor
# 20195,Ricoh,Ricoh GXR Systemkamera,"S10 Kit inkl. 1:2,5-4,4/24-72 mm VC Objektiv"
# 20195,Ricoh,Ricoh GXR Systemkamera,"S10 Kit inkl. 1:2,5-4,4/24-72 mm VC Objektiv"
# 20195,Ricoh,"Ricoh GXR Systemkamera (10 Megapixel, 10-fach optischer Zoom, 7,6 cm (3 Zoll) Display, HD Video) Geh�use schwarz",
# 20195,Ricoh,"Ricoh GXR Systemkamera (10 Megapixel, 10-fach optischer Zoom, 7,6 cm (3 Zoll) Display, HD Video) Geh�use schwarz",
# 20195,Ricoh,"Ricoh GXR Systemkamera (10 Megapixel, 10-fach optischer Zoom, 7,6 cm (3 Zoll) Display, HD Video) Geh�use schwarz",
# 20195,Ricoh,"Ricoh GXR Systemkamera (10 Megapixel, 10-fach optischer Zoom, 7,6 cm (3 Zoll) Display, HD Video) Kit inkl. P10 28-300mm Objektiv",
# 20195,Ricoh,"Ricoh GXR Systemkamera (10 Megapixel, 10-fach optischer Zoom, 7,6 cm (3 Zoll) Display, HD Video) Kit inkl. P10 28-300mm Objektiv",
#
# Analysis: 
# 
# There are 20 listings.
# However only one of these was specifically for the A12 lens combination (and that could only be determined from the extraProdDetails column).
# So do these count as 20 potential matches? Or 19 mismatches and 1 match?
# 
# Conclusion: 
# 
# Since errors are penalized more than correct matches, it is probably not worth it.
# 
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# b. Classification: +c_a
# 
# Products:
#   manufacturer  family  model
#   Contax                N Digital
# 
# All unmatched listings for Contax:
# 
# index_l,pManuf,productDesc,extraProdDetails
# 20195,Contax,Syntax Vivitar 2 Gb 6MP 3X Optical 4X Digital Zoom,
# 20195,Contax,Vivitar VIVICAM-8400 8.0 MegaPixel Camera,3x Optical Zoom and 2.0 Inch TFT LCD
# 20195,Contax,Vivitar VIVICAM-8400 8.0 MegaPixel Camera,3x Optical Zoom and 2.0 Inch TFT LCD
#
# Conclusion: No new matches will be found.
# 
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# c. Classification: +c_a_a
# 
# Products:
#   manufacturer  family  model
#   Ricoh                 GR Digital III
# 
# Unmatched listings that might be relevant:
# 
# index_l,pManuf,productDesc,extraProdDetails
# 20195,Ricoh,Ricoh - GRD III - Appareil photo numerique - 10 Mpix - Noir,
# 20195,Ricoh,Ricoh - GRD III - Appareil photo numerique - 10 Mpix - Noir,
# 20195,Ricoh,Ricoh - Objectif GR LENS A12 28 mm F2.5,
# 20195,Ricoh,Ricoh - Objectif GR LENS A12 28 mm F2.5,
# 20195,Ricoh,Ricoh A12 GR - Digital camera lens unit - prosumer - 12.3 Mpix,
# 20195,Ricoh,"Ricoh GR Digital - Digital camera - compact - 8.1 Mpix - supported memory: MMC, SD",
# 20195,Ricoh,"Ricoh GR Digital - Digital camera - compact - 8.1 Mpix - supported memory: MMC, SD",
# 20195,Ricoh,"Ricoh GR Digital 2 Digitalkamera (10 Megapixel, 6,9 cm (2,7 Zoll) Display) schwarz",
# 20195,Ricoh,"Ricoh GR Digital 2 Digitalkamera (10 Megapixel, 6,9 cm (2,7 Zoll) Display) schwarz",
# 
# Analysis: 
# 
# The "GRD III" listings are probably the only correct matches.
# They will be a low match, because the rule used will be "Word and number crossing family and model"
# The other matches have different MP ratings, so will most likely be filtered out.
# 
# Conclusion: Not worth it.
# 
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# 
# OVERALL CONCLUSION: 
# 
# It is not worth adding a rule to treat a model classification that starts with 'c_' as a product code.
# 


# -----------------------------------------------------------------------------
# 12.3 Join unmatched listings to products based on manufacturers 
#      and numbers extracted from the listings and products:
# 

unmatched_listing_numbers = unmatched_listings.productDesc.str.findall('(^\d+|(?<=\s)\d+)(?=\s|$)')
unmatched_listings['first_number'] = unmatched_listing_numbers.str.get(0)
product_numbers = products.model.str.findall('(^\d+|(?<=\s)\d+)(?=\s|$)')
products['first_number'] = product_numbers.str.get(0)

unmatched_listings_and_products_by_first_number = pd.merge(
    left=unmatched_listings,
    right=products[['manufacturer', 'family', 'model', 'first_number']],
    how='inner',
    left_on=['pManuf', 'first_number'],
    right_on=['manufacturer', 'first_number'],
    suffixes=('_l', '_r')
)

unmatched_listings_and_products_by_first_number \
    = unmatched_listings_and_products_by_first_number[ \
        unmatched_listings_and_products_by_first_number.first_number.notnull()]

unmatched_listings_and_products_by_first_number.to_csv(
    '../data/intermediate/unmatched_listings_and_products_by_first_number.csv', 
    encoding='utf-8')

# POSSIBLE NEW MATCHES:
# 
# The only potential new listings found were to the Olympus mju Tough 8010 product.
# There were 8 unmatched listings similar to the following: OLYMPUS [mju:] Tough 8010 - black
# 
# Thus 8 new listings could arise from matching a "..._a_n" product code
# 
# CONCLUSION:
# 
# It is not worth adding this rule for the sake of just 8 new listings.
# 



# ==============================================================================
# 13. Export the resulting matches as a json file:
#

# -----------------------------------------------------------------------------
# 13.1 Create output folder:
# 

folder_data_output = '../data/output'

if not os.path.exists(folder_data_output):
    os.makedirs(folder_data_output)

# -----------------------------------------------------------------------------
# 13.2 Generate result objects:
# 

def generate_json_listings_for_product(prod_grp):
    original_listing_indices = prod_grp['original_listing_index'].values.tolist()
    listings = [listingData[oli] for oli in original_listing_indices]
    return listings

listings_with_matched_products_by_product_name = listings_with_matched_products.groupby('product_name')
listings_by_product_name = listings_with_matched_products_by_product_name.apply(generate_json_listings_for_product)
listings_by_product_name_df = DataFrame({'listings' : listings_by_product_name})

listings_by_product_name_df.to_csv('../data/intermediate/listings_by_product_name.csv', encoding='utf-8')

listings_by_all_product_names = pd.merge(
    products[['product_name']],
    listings_by_product_name_df,
    how='left',
    left_on='product_name',
    right_index=True
).sort_index(by='product_name')

def generate_json_product_dict(row):
    product_name = row['product_name']
    listings = row['listings']
    if not (type(listings) is list):
        listings = []
    product_dict = {
        "product_name": product_name,
        "listings": listings
    }
    return json.dumps(product_dict, encoding='utf-8', ensure_ascii=False)

results = listings_by_all_product_names.apply(generate_json_product_dict, axis=1).values.tolist()

# -----------------------------------------------------------------------------
# 13.3 Write result objects to a file:
# 

results_file_contents = u'\n'.join(results)
results_file = codecs.open(folder_data_output + '/results.txt', 'w', 'utf-8')

with results_file as f:
    f.write(results_file_contents)
