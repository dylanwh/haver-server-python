#!/usr/bin/perl
use strict;
use warnings;
use IO::Socket;
use YAML;

my (@commands, @extensions, @failures);
my $sock;

for (1 .. 100) {
	$sock = new IO::Socket::INET(PeerAddr => 'localhost:7575');
	if ($sock) {
		last;
	}
	sleep 10;
}
die "Unable to connect!\n" unless $sock;

$sock->print("HAVER\thaverdoc\r\n");
$sock->print("IDENT\thaverdoc$$\r\n");
$sock->print("HELP:COMMANDS\r\n");
$sock->print("HELP:FAILURES\r\n");
$sock->print("POKE\tlast\n");

while (my $line = $sock->getline) {
	warn "S: $line";
	my ($cmd, @args) = parse($line);
	if ($cmd eq 'HELP:COMMANDS') {
		@commands = @args;
	} elsif ($cmd eq 'HELP:FAILURES') {
		@failures = @args;
	} elsif ($cmd eq 'HAVER') {
		@extensions = split(/,/, $args[2]);
	} elsif ($cmd eq 'HELLO') {
		warn "Logged in\n";
	} elsif ($cmd eq 'OUCH') {
		last;
	} else {
		die "WTF? $cmd\n";
	}
}

my %commands;
foreach my $cmd (@commands) {
	warn "Querying $cmd\n";
	$sock->print("HELP:COMMAND\t$cmd\n");
	my ($cmd2, $cmd3, @args) = parse($sock->getline);
	if ($cmd2 eq 'HELP:COMMAND') {
		if (@args % 2 == 1) {
			warn "odd number for $cmd3: @args\n";
		}
		$commands{$cmd3} = { @args };
		$commands{$cmd3}{FAILURES} = [ split(/,/, $commands{$cmd3}{FAILURES})]
	} else {
		die "WTF? $cmd2\n";
	}
}

my %failures;
foreach my $fail (@failures) {
	warn "Querying $fail\n";
	$sock->print("HELP:FAILURE\t$fail\n");
	my ($cmd, $fail, $desc) = parse($sock->getline);
	if ($cmd eq 'HELP:FAILURE') {
		$failures{$fail} = $desc;
	} else {
		die "WTF? $cmd\n";
	}
}

print Dump({
		lists => {
			command => \@commands,
			failure => \@failures,
			extension => \@extensions,
		},
		commands => \%commands,
		failures => \%failures,
	});


sub parse {
	my $line = shift;
	$line =~ s/\r\n$//g;
	split(/\t/, $line);
}
