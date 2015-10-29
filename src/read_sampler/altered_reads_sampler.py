from argparse import ArgumentParser
import random
import sys
import itertools
from helpers.logger import init_logger

sys.path.extend(['/Users/hayssam/Documents/MICADo/src'])
from helpers.helpers import data_dir, time_iterator
import pandas as pd
from pyparsing import Word, OneOrMore, Group

pd.set_option('display.width', 250)

__author__ = 'hayssam'

logger=init_logger(name="READSAMPLER")

##### cigar parser
def convertIntegers(tokens):
	return int(tokens[0])


alt_type = "SIMD"
digits = "0123456789"
an_alt = Word(alt_type)
alt_length = Word(digits).setParseAction(convertIntegers)
alt_and_length = Group(alt_length + an_alt)
cigar_string = OneOrMore(alt_and_length)


# cigar_string.parseString("76M1I257M1I22M1I99M")
# % timeit cigar_string.parseString("76M1I257M1I22M1I99M")[1]


# convert coordinates
def coordinate_map(an_alignment_row):
	all_ranges = []
	cigar = an_alignment_row.CIGAR
	start_pos = an_alignment_row.POS
	label = an_alignment_row.QNAME
	read_start_range = (0, 0)
	ref_start_range = (start_pos, start_pos)
	read_last_range = read_start_range
	ref_last_range = ref_start_range
	for length, type in cigar_string.parseString(cigar):
		if type == "M":
			read_current_range = (read_last_range[1], read_last_range[1] + length)
			ref_current_range = (ref_last_range[1], ref_last_range[1] + length)
		elif type == "I":
			read_current_range = (read_last_range[1], read_last_range[1] + length)
			ref_current_range = (ref_last_range[1], ref_last_range[1])
		elif type == "D":
			read_current_range = (read_last_range[1], read_last_range[1])
			ref_current_range = (ref_last_range[1], ref_last_range[1] + length)
		elif type == "S":
			read_current_range = (read_last_range[1], read_last_range[1] + length)
			ref_current_range = (ref_last_range[1], ref_last_range[1])
		all_ranges.append({"label": label, "type": type, "length": length, "ref_coord": ref_current_range, "read_coord": read_current_range})
		read_last_range = read_current_range
		ref_last_range = ref_current_range
	return all_ranges


def random_alteration(start, end):
	# sample a position
	MAX_LEN = 5
	a_pos = random.randint(start, end - MAX_LEN)
	a_type = random.choice("IMD")
	a_length = random.randint(1, 5)
	a_content = "".join([random.choice("actg") for i in range(a_length)])
	a_qual = "q" * a_length
	if a_type == "D":
		return (a_pos, a_pos + a_length - 1), (a_type, None, None)
	elif a_type == "I":
		return (a_pos, a_pos), (a_type, a_content, a_qual)
	else:
		return (a_pos, a_pos + a_length - 1), (a_type, a_content, a_qual)


# find all regions containing the sampled pos
def region_overlap(x, y):
	return x[0] <= y[1] and y[0] <= x[1]


def region_overlap_right_strict(x, y):
	return x[0] <= y[1] and y[0] < x[1]


def transform_coordinate(ref_range, read_range, pos):
	return read_range[0] + (pos[0] - ref_range[0]), read_range[0] + (pos[1] - ref_range[0])


def mutating_sequence_iterator(read_label, alterations=None, output="seq"):
	if not alterations:
		alterations = {}
	global all_ranges, aligned_reads
	if output == "seq":
		read_sequence = aligned_reads.ix[read_label].SEQ
	else:
		read_sequence = aligned_reads.ix[read_label].QUAL
	# coord_map = pd.DataFrame.from_records(coordinate_map(aligned_reads.ix[read_label]))
	coord_map = all_ranges.ix[read_label]
	if len(coord_map.shape) == 1:  # we only had one row, make it a DF
		coord_map = pd.DataFrame([coord_map])

	read_length = len(read_sequence)
	read_alterations = {}
	for alt_ref_coord, alt in alterations.items():
		affected_regions = coord_map[coord_map.ref_coord.apply(lambda r: region_overlap_right_strict(r, alt_ref_coord))].query("type=='M'")
		# translate alteration map to read coordinate
		for i, region in affected_regions.iterrows():
			read_coordinates = transform_coordinate(region.ref_coord, region.read_coord, alt_ref_coord)
			read_alterations[read_coordinates] = alt

	current_read_position = 0
	while current_read_position < read_length:
		base_is_covered = False

		for read_coord, (alt_type, alt, qual) in read_alterations.items():

			if (read_coord[0] <= current_read_position) and (current_read_position <= read_coord[1]):
				# map to qual
				if output == "qual":
					alt_seq = qual
				else:
					alt_seq = alt
				if alt_type == "M":
					base_is_covered = True
					for alt_i, i in enumerate(range(read_coord[0], read_coord[1] + 1)):
						yield alt_seq[alt_i]
						current_read_position += 1
				elif alt_type == "I":
					for base in alt_seq:
						yield base
				elif alt_type == "D":
					base_is_covered = True
					for alt_i, i in enumerate(range(read_coord[0], read_coord[1] + 1)):
						current_read_position += 1
				break
		if base_is_covered:
			# current_read_position += 1
			continue
		yield read_sequence[current_read_position]
		# print read_sequence[current_read_position],
		current_read_position += 1
	raise StopIteration


def build_a_sample(n_reads, fraction_altered, n_alterations, output_file_prefix="data/synthetic/test0"):
	global all_ranges
	# n_reads = 100
	# n_alterations = 2
	# fraction_altered = 0.5
	# sample some reads
	sub_reads = aligned_reads.sample(n_reads)

	all_ranges = []

	for i, an_alignment in sub_reads.iterrows():
		all_ranges.extend(coordinate_map(an_alignment))
	logger.info("Mapped coordinates to reference")
	all_ranges = pd.DataFrame.from_records(all_ranges)
	all_ranges.set_index("label", inplace=True)
	ref_start = min([min(x) for x in all_ranges.ref_coord])
	ref_end = max([max(x) for x in all_ranges.ref_coord])

	some_alterations = dict([random_alteration(ref_start, ref_end) for i in range(n_alterations)])
	altered_reads = list(sub_reads.sample(int(len(sub_reads) * fraction_altered)).QNAME)
	non_altered_reads = set(sub_reads.QNAME).difference(altered_reads)

	logger.info("Generated alterations")

	def clean_label(lbl):
		return lbl.replace("/", "_")

	with open(output_file_prefix + "_non_alt.fastq", "w") as f:
		for i,read_label in time_iterator(sub_reads.QNAME,logger,msg_prefix="Generating non altered fastq, non altered reads"):
			print >> f, "@%s" % (clean_label(read_label)) + "_ORIG"
			print >> f, sub_reads.ix[read_label].SEQ
			print >> f, "+"
			print >> f, sub_reads.ix[read_label].QUAL
			print >> f, "\n"

	with open(output_file_prefix + ".fastq", "w") as f:
		for i,read_label in time_iterator(altered_reads,logger,msg_prefix="Generating altered fastq, altered reads"):
			print >> f, "@%s" % (clean_label(read_label)) + "_ALT"
			print >> f, "".join(mutating_sequence_iterator(read_label=read_label, alterations=some_alterations))
			print >> f, "+"
			print >> f, "".join(mutating_sequence_iterator(read_label=read_label, alterations=some_alterations, output="qual"))
			print >> f, "\n"
		for i,read_label in time_iterator(non_altered_reads,logger,msg_prefix="Generating altered fastq, non altered reads"):
			print >> f, "@%s" % (clean_label(read_label)) + "_ORIG"
			print >> f, sub_reads.ix[read_label].SEQ
			print >> f, "+"
			print >> f, sub_reads.ix[read_label].QUAL
			print >> f, "\n"
	with open(output_file_prefix + ".alterations.txt", "w") as f:
		for coord, alt in some_alterations.items():
			print >> f, "\t".join(map(str, coord)) + " " + "\t".join(map(str, alt))
	logger.info("finished generation for %d reads, %d alterations, output files are",n_reads,n_alterations)
	logger.info("%s: Original sampled reads",output_file_prefix + "_non_alt.fastq")
	logger.info("%s: Altered sampled reads",output_file_prefix + ".fastq")
	logger.info("%s: Alterations description",output_file_prefix + ".alterations.txt")
	logger.info("Alterations are %s",some_alterations)


if __name__ == '__main__':
	parser = ArgumentParser()
	parser.add_argument('--n_reads', help='Number of reads for the generated sample', default=500, type=int, required=False)
	parser.add_argument('--fraction_altered', help='Fraction (between 0 and 1) of reads that should have recurrent alterations', required=False, type=float, default=0.1)
	parser.add_argument('--n_alterations', help='Number of alterations to insert', required=False, type=int, default=1)
	parser.add_argument('--output_file_prefix', help='output file prefix', required=True, type=str)
	parser.add_argument('--input_sam', help='Input SAM file', required=True, type=str)
	args = parser.parse_args()
	# starting_file = data_dir + "/alignments/C_model_GMAPno40_NM_000546.5.sam"
	starting_file = args.input_sam
	logger.info("Will parse input SAM")
	aligned_reads = pd.DataFrame.from_csv(starting_file, sep="\t", header=5, index_col=None)
	SAM_COLUMNS = ["QNAME", "FLAG", "RNAME", "POS", "MAPQ", "CIGAR", "RNEXT", "PNEXT", "TLEN", "SEQ", "QUAL"]
	this_columns = SAM_COLUMNS + ["custom_%d" % i for i in range(len(SAM_COLUMNS), aligned_reads.shape[1])]
	aligned_reads.columns = this_columns
	aligned_reads.set_index("QNAME", drop=False, inplace=True)
	logger.info("Starting reads generation")
	build_a_sample(n_reads=args.n_reads, n_alterations=args.n_alterations, fraction_altered=args.fraction_altered, output_file_prefix=args.output_file_prefix)