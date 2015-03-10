# ST2/ST3 compat
from __future__ import print_function
import sublime
if sublime.version() < '3000':
    # we are on ST2 and Python 2.X
	_ST3 = False
	import getTeXRoot
	import jump_aux
else:
	_ST3 = True
	from . import getTeXRoot
	from . import jump_aux


import sublime_plugin, os.path, subprocess, time, re, codecs


# Jump to current line in PDF file
# NOTE: must be called with {"from_keybinding": <boolean>} as arg
class jump_to_pdfCommand(sublime_plugin.TextCommand):
	# Attempt to map a line number in a .lytex file to its corresponding line number
	# in the LilyPond-generated .tex file.
	def map_lytex2tex(self, old_line, fileName):
		# Ensure that both files (.tex and .lytex) are open.
		tex = codecs.open(fileName + u'.tex', "r", "UTF-8", "ignore")
		lytex = codecs.open(fileName + u'.lytex', "r", "UTF-8", "ignore")

		# Initialize the line number offset (iteratively computed as "cur_sigma").
		cur_sigma = 0

		# Initialize line number registers:
		# i, ii hold the line numbers opening and closing, respectively, the most recently scanned  "lilypond" environment in the .lytex file.
		# j, jj hold the line numbers opening and closing, respectively, the corresponding code block generated by lilypond-book in the .tex file.
		i = ii = j = jj = g = -1
		# print ("old_line = ", old_line)

		# Find the opening and closing line numbers of the next LilyPond hunk in the .tex and .lytex files.
		while ii < old_line:
			i, r = jump_aux.line_of_next_occurrence(lytex, ii, jump_aux.lytex_scope_open_regex, True)
			# print ("i = ", i)
			ii, r = jump_aux.line_of_next_occurrence(lytex, i, jump_aux.lytex_scope_close_regex, True)
			# print ("ii = ", ii)
			j, r = jump_aux.line_of_next_occurrence(tex, jj, jump_aux.lytex_scope_open_regex, True)
			# print ("j = ", j)
			jj, r = jump_aux.line_of_next_occurrence(tex, j, jump_aux.lytex_scope_close_regex, True)
			# print ("jj = ", jj)
			cur_sigma = cur_sigma + (ii - i - (jj - j))
			# print ("cur_sigma = ", cur_sigma)

		# The previous loop has stopped at the Lilypond hunk immediately following the cursor. Revoke the last iteration to account only for hunks before the cursor.
		cur_sigma = cur_sigma - (ii - i - (jj - j))		# print ("cur_sigma (adjusted) = ", cur_sigma)

		# Preliminarily calculate at which line the old_line of the .texly maps into the .tex.
		mapping = old_line - cur_sigma

		# Find line where Lilypond has injected stuff into the preamble of the .tex file.
		tex.seek(0)
		g = jump_aux.line_of_next_occurrence(tex, g, jump_aux.lily_packages)
		# print ("Preamble addition found at .tex line #", g[0])

		# Add +1 to the preliminary mapping if the \usepackage{graphics} line of the .tex file is located before the mapping.
		# This last calculation yields the exact mapping.
		if mapping < g[0]:
			# print ("mapping < g. Mapping = ", mapping)
			return mapping
		else:
			# print ("mapping >= g. Mapping = ", mapping)
			return mapping + 1

	def run(self, edit, **args):
		# Check prefs for PDF focus and sync
		s = sublime.load_settings("LaTeXTools Preferences.sublime-settings")
		prefs_keep_focus = s.get("keep_focus", True)
		keep_focus = self.view.settings().get("keep focus",prefs_keep_focus)
		prefs_forward_sync = s.get("forward_sync", True)
		forward_sync = self.view.settings().get("forward_sync",prefs_forward_sync)

		prefs_lin = s.get("linux")

		# If invoked from keybinding, we sync
		# Rationale: if the user invokes the jump command, s/he wants to see the result of the compilation.
		# If the PDF viewer window is already visible, s/he probably wants to sync, or s/he would have no
		# need to invoke the command. And if it is not visible, the natural way to just bring up the
		# window without syncing is by using the system's window management shortcuts.
		# As for focusing, we honor the toggles / prefs.
		from_keybinding = args["from_keybinding"]
		if from_keybinding:
			forward_sync = True
		print (from_keybinding, keep_focus, forward_sync)

		texFile, texExt = os.path.splitext(self.view.file_name())
		if texExt.upper() not in (".TEX", ".LYTEX"):
			sublime.error_message("%s is not a TeX source file: cannot jump." % (os.path.basename(self.view.file_name()),))
			return
		quotes = "\""
		srcfile = texFile + u'.tex'
		root = getTeXRoot.get_tex_root(self.view)
		print ("!TEX root = ", repr(root) ) # need something better here, but this works.
		rootName, rootExt = os.path.splitext(root)
		pdffile = rootName + u'.pdf'
		(line, col) = self.view.rowcol(self.view.sel()[0].end())
		# If we are mapping from a .LYTEX file to the PDF, we need to map to the .TEX file first.
		if texExt.upper() == ".LYTEX":
			line = self.map_lytex2tex(line, texFile.upper())
			# print ("New line: ", line)
		print ("Jump to ", line,col, "of ", srcfile)
		# column is actually ignored up to 0.94
		# HACK? It seems we get better results incrementing line
		line += 1

		# Query view settings to see if we need to keep focus or let the PDF viewer grab it
		# By default, we respect settings in Preferences


		# platform-specific code:
		plat = sublime_plugin.sys.platform
		if plat == 'darwin':
			options = ["-r","-g"] if keep_focus else ["-r"]
			if forward_sync:
				subprocess.Popen(["/Applications/Skim.app/Contents/SharedSupport/displayline"] +
								options + [str(line), pdffile, srcfile])
			else:
				skim = os.path.join(sublime.packages_path(),
								'LyTeXTools', 'skim', 'displayfile')
				subprocess.Popen(['sh', skim] + options + [pdffile])
		elif plat == 'win32':
			# determine if Sumatra is running, launch it if not
			print ("Windows, Calling Sumatra")
			# hide console
			# NO LONGER NEEDED with new Sumatra?
			# startupinfo = subprocess.STARTUPINFO()
			# startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
			# tasks = subprocess.Popen(["tasklist"], stdout=subprocess.PIPE,
			# 		startupinfo=startupinfo).communicate()[0]
			# # Popen returns a byte stream, i.e. a single line. So test simply:
			# # Wait! ST3 is stricter. We MUST convert to str
			# tasks_str = tasks.decode('UTF-8') #guess..
			# if "SumatraPDF.exe" not in tasks_str:
			# 	print ("Sumatra not running, launch it")
			# 	self.view.window().run_command("view_pdf")
			# 	time.sleep(0.5) # wait 1/2 seconds so Sumatra comes up
			setfocus = 0 if keep_focus else 1
			# First send an open command forcing reload, or ForwardSearch won't
			# reload if the file is on a network share
			# command = u'[Open(\"%s\",0,%d,1)]' % (pdffile,setfocus)
			# print (repr(command))
			# self.view.run_command("send_dde",
			# 		{ "service": "SUMATRA", "topic": "control", "command": command})
			# Now send ForwardSearch command if needed
			if forward_sync:
				subprocess.Popen(["SumatraPDF.exe","-reuse-instance","-forward-search", srcfile, str(line), pdffile])
				# command = "[ForwardSearch(\"%s\",\"%s\",%d,%d,0,%d)]" \
				# 			% (pdffile, srcfile, line, col, setfocus)
				# print (command)
				# self.view.run_command("send_dde",
				# 		{ "service": "SUMATRA", "topic": "control", "command": command})


		elif 'linux' in plat: # for some reason, I get 'linux2' from sys.platform
			print ("Linux!")

			# the required scripts are in the 'evince' subdir
			ev_path = os.path.join(sublime.packages_path(), 'LaTeXTools', 'evince')
			ev_fwd_exec = os.path.join(ev_path, 'evince_forward_search')
			ev_sync_exec = os.path.join(ev_path, 'evince_sync') # for inverse search!
			#print ev_fwd_exec, ev_sync_exec

			# Run evince if either it's not running, or if focus PDF was toggled
			# Sadly ST2 has Python <2.7, so no check_output:
			running_apps = subprocess.Popen(['ps', 'xw'], stdout=subprocess.PIPE).communicate()[0]
			# If there are non-ascii chars in the output just captured, we will fail.
			# Thus, decode using the 'ignore' option to simply drop them---we don't need them
			running_apps = running_apps.decode(sublime_plugin.sys.getdefaultencoding(), 'ignore')

			# Run scripts through sh because the script files will lose their exec bit on github

			# Get python binary if set:
			py_binary = prefs_lin["python2"] or 'python'
			sb_binary = prefs_lin["sublime"] or 'sublime-text'
			# How long we should wait after launching sh before syncing
			sync_wait = prefs_lin["sync_wait"] or 1.0

			evince_running = ("evince " + pdffile in running_apps)
			if (not keep_focus) or (not evince_running):
				print ("(Re)launching evince")
				subprocess.Popen(['sh', ev_sync_exec, py_binary, sb_binary, pdffile], cwd=ev_path)
				print ("launched evince_sync")
				if not evince_running: # Don't wait if we have already shown the PDF
					time.sleep(sync_wait)
			if forward_sync:
				subprocess.Popen([py_binary, ev_fwd_exec, pdffile, str(line), srcfile])
		else: # ???
			pass