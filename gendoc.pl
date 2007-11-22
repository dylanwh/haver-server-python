#!/usr/bin/perl
use strict;
use warnings;
use YAML;

local $/ = undef;
my $s = <>;
my %data = %{ Load($s) };

print "COMMANDS:\n";
foreach my $cmd (sort keys %{ $data{commands} }) {
	print "C: $cmd  $data{commands}{$cmd}{ARGS}\n";
	print "   $data{commands}{$cmd}{DESC}\n";
	print "   Extension: $data{commands}{$cmd}{EXTENSION}\n";
	print "   Possible FAILs: ", join(', ', @{ $data{commands}{$cmd}{FAILURES} }), "\n";
	print "   Possible replies:\n";
	foreach my $reply (@{ $data{commands}{$cmd}{REPLIES} }) {
		print "      $reply\n";
	}
	print "\n";
}

print "\nFAILURES:\n";
foreach my $fail (sort keys %{ $data{failures} }) {
	print "$fail:\n\t$data{failures}{$fail}\n";
}

