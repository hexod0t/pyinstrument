# -*- coding: utf-8 -*-
import os, sys, json, time
import pyinstrument
from pyinstrument import processors
from pyinstrument.util import truncate
try:
    from html import escape as html_escape
except ImportError:
    from cgi import escape as html_escape


class Renderer(object):
    def __init__(self, processor_options=None):
        # processors is defined on the base class to provide a common way for users to
        # add to and manipulate them before calling render()
        self.processors = self.default_processors()
        self.processor_options = processor_options or {}

    def default_processors(self):
        ''' 
        Return a list of processors that this renderer uses by default
        '''
        raise NotImplementedError()

    def preprocess(self, root_frame):
        frame = root_frame
        for processor in self.processors:
            frame = processor(frame, options=self.processor_options)
        return frame

    def render(self, session):
        '''
        Return a string that contains the rendered form of `frame`
        '''
        raise NotImplementedError()


class ConsoleRenderer(Renderer):
    def __init__(self, unicode=False, color=False, show_all=False, **kwargs):
        super(ConsoleRenderer, self).__init__(**kwargs)

        self.unicode = unicode
        self.color = color
        self.colors = self.colors_enabled if color else self.colors_disabled
        if show_all:
            self.processors.remove(processors.group_library_frames_processor)

    def render(self, session):
        result = self.render_preamble(session)

        self.root_frame = self.preprocess(session.root_frame())
        result += self.render_frame(self.root_frame)
        result += '\n'

        return result

    # pylint: disable=W1401
    def render_preamble(self, session):
        lines = [
            "",
            "              _          __                          __ ",
            "   ___  __ __(_)__  ___ / /_______ ____ _  ___ ___  / /_",
            "  / _ \/ // / / _ \(_-</ __/ __/ // /  ' \/ -_) _ \/ __/",
            " / .__/\_, /_/_//_/___/\__/_/  \_,_/_/_/_/\__/_//_/\__/ ",
            "/_/   /___/                 {:>26}  ".format(pyinstrument.__version__)
        ]


        lines[2] += "    Recorded:  %s" % time.strftime('%X', time.localtime(session.start_time))
        lines[3] += "    Samples:   %s" % session.sample_count
        lines[4] += "    Duration:  {:.3n}".format(session.duration)
        if session.cpu_time is not None:
            lines[5] += "    CPU time:  {:.3n}".format(session.cpu_time)

        lines.append('')
        lines.append('Program: %s' % session.program)
        lines.append('')
        lines.append('')

        return '\n'.join(lines)

    def render_frame(self, frame, indent=u'', child_indent=u''):
        if not frame.group or (frame.group.root == frame
                               or frame.self_time > 0.2*self.root_frame.time()
                               or frame in frame.group.exit_frames):
            time_str = (self._ansi_color_for_time(frame)
                        + '{:.3f}'.format(frame.time()) 
                        + self.colors.end)
            function_color = self._ansi_color_for_function(frame)
            result = u'{indent}{time_str} {function_color}{function}{c.end}  {c.faint}{code_position}{c.end}\n'.format(
                indent=indent,
                time_str=time_str,
                function_color=function_color,
                function=frame.function,
                code_position=frame.code_position_short,
                c=self.colors)
            if self.unicode:
                indents = {'├': u'├─ ', '│': u'│  ', '└': u'└─ ', ' ': u'   '}
            else:
                indents = {'├': u'|- ', '│': u'|  ', '└': u'`- ', ' ': u'   '}

            if frame.group and frame.group.root == frame:
                result += u'{indent}[{count} frames hidden]  {c.faint}{libraries}{c.end}\n'.format(
                    indent=child_indent+u'   ',
                    count=len(frame.group.frames),
                    libraries=truncate(', '.join(frame.group.libraries), 40),
                    c=self.colors)
                for key in indents:
                    indents[key] = u'      '
        else:
            result = ''
            indents = {'├': u'', '│': u'', '└': u'', ' ': u''}

        children = [f for f in frame.children if f.proportion_of_total > 0.01]

        if children:
            last_child = children[-1]

        for child in children:
            if child is not last_child:
                c_indent = child_indent + indents['├']
                cc_indent = child_indent + indents['│']
            else:
                c_indent = child_indent + indents['└']
                cc_indent = child_indent + indents[' ']
            result += self.render_frame(child, indent=c_indent, child_indent=cc_indent)

        return result

    def _ansi_color_for_time(self, frame):
        if frame.proportion_of_total > 0.6:
            return self.colors.red
        elif frame.proportion_of_total > 0.2:
            return self.colors.yellow
        elif frame.proportion_of_total > 0.05:
            return self.colors.green
        else:
            return self.colors.bright_green + self.colors.faint

    def _ansi_color_for_function(self, frame):
        if frame.is_application_code:
            return self.colors.bg_dark_blue_255+self.colors.white_255
        else:
            return ''

    def default_processors(self):
        return processors.default_time_aggregate_processors()
     
    class colors_enabled:
        red = '\033[31m'
        green = '\033[32m'
        yellow = '\033[33m'
        blue = '\033[34m'
        cyan = '\033[36m'
        bright_green = '\033[92m'
        white = '\033[37m\033[97m'

        bg_dark_blue_255 = '\033[48;5;24m'
        white_255 = '\033[38;5;15m'

        bold = '\033[1m'
        faint = '\033[2m'

        end = '\033[0m'


    class colors_disabled:
        def __getattr__(self, key):
            return ''

    colors_disabled = colors_disabled()


class HTMLRenderer(Renderer):
    def render(self, session):
        frame = self.preprocess(session.root_frame())

        resources_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources/')

        with open(os.path.join(resources_dir, 'style.css')) as f:
            css = f.read()

        with open(os.path.join(resources_dir, 'profile.js')) as f:
            js = f.read()

        with open(os.path.join(resources_dir, 'jquery-1.11.0.min.js')) as f:
            jquery_js = f.read()

        body = self.render_frame(frame)

        page = '''
            <html>
            <head>
                <style>{css}</style>
                <script>{jquery_js}</script>
            </head>
            <body>
                {body}
                <script>{js}</script>
            </body>
            </html>'''.format(css=css, js=js, jquery_js=jquery_js, body=body)

        return page

    def render_frame(self, frame):
        children = frame.children
        start_collapsed = all(child.proportion_of_total < 0.1 for child in children)

        extra_class = ''
        extra_class += 'collapse ' if start_collapsed else ''
        extra_class += 'no_children ' if not frame.children else ''
        extra_class += 'application ' if frame.is_application_code else ''

        result = '''<div class="frame {extra_class}" data-time="{time}" date-parent-time="{parent_proportion}">
            <div class="frame-info">
                <span class="time">{time:.3f}s</span>
                <span class="total-percent">{total_proportion:.1%}</span>
                <!--<span class="parent-percent">{parent_proportion:.1%}</span>-->
                <span class="function">{function}</span>
                <span class="code-position">{code_position}</span>
            </div>'''.format(
                time=frame.time(),
                function=html_escape(frame.function),  # pylint: disable=W1505
                code_position=html_escape(frame.code_position_short),  # pylint: disable=W1505
                parent_proportion=frame.proportion_of_parent,
                total_proportion=frame.proportion_of_total,
                extra_class=extra_class)

        result += '<div class="frame-children">'

        # add this filter to prevent the output file getting too large
        children = [f for f in children if f.proportion_of_total > 0.005]

        for child in children:
            result += self.render_frame(child)

        result += '</div></div>'

        return result

    def default_processors(self):
        return processors.default_time_aggregate_processors()


class JSONRenderer(Renderer):
    @staticmethod
    def render_frame(frame):
        return {
            'function': frame.function,
            'file_path_short': frame.file_path_short,
            'file_path': frame.file_path,
            'line_no': frame.line_no,
            'time': frame.time(),
            'children': [JSONRenderer.render_frame(frame) for frame in frame.children]
        }

    def render(self, session):
        frame = self.preprocess(session.root_frame())
        return json.dumps(JSONRenderer.render_frame(frame), indent=2)

    def default_processors(self):
        return processors.default_time_aggregate_processors()
