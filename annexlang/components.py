import yaml
from itertools import chain
import re

object_counter = 0


# We use this counter to number the protocol steps. The counter can be manually set to a different value.
def count(start=0, step=1):
    # count(10) --> 10 11 12 13 14 ...
    # count(2.5, 0.5) -> 2.5 3.0 3.5 ...
    n = start
    while True:
        new_val = yield n
        if new_val:
            n = new_val
        else:
            n += step

            
class cached_property(object):
    """
    Descriptor (non-data) for building an attribute on-demand on first use.
    """
    def __init__(self, factory):
        """
        <factory> is called such: factory(instance) to build the attribute.
        """
        self._attr_name = factory.__name__
        self._factory = factory

    def __get__(self, instance, owner):
        # Build the attribute.
        attr = self._factory(instance)

        # Cache the value; hide ourselves.
        setattr(instance, self._attr_name, attr)

        return attr

    
class ProtocolObject(yaml.YAMLObject):
    def __new__(cls):
        global object_counter
        object_counter += 1

        obj = super().__new__(cls)
        obj.annexid = "{}_{}".format(cls.__name__, object_counter)

        return obj

    @staticmethod
    def get_pos(column, line):
        return f"pos-{column}-{line}"

    def __repr__(self):
        return f"""<{self.annexid}>"""

    def html_j2(self, protocol):
        if not hasattr(self, 'html_template'):
            print ("Step type not yet supported in HTML, will be ignored: " + self.annexid)
            return ''
        if hasattr(self, 'html_warning'):
            print ("Step type not yet supported in HTML, will not be shown correctly: " + self.annexid)
        from jinja2 import Environment, BaseLoader  # only loading this if html output is desired
        template = Environment(loader=BaseLoader).from_string(self.html_template)
        return template.render({'this': self, 'protocol': protocol})


    
class ProtocolStep(ProtocolObject):
    node_name_counter = 0
    skip_number = 0
    text_style = "annex_arrow_text"
    _affecting_nodes = []
    style = ""
    counter = None  # manually set number of this protocol step, if any
    
    def length(self):
        return 1

    def tikz_desc(self):
        return f"""% drawing node of type {self.__class__.__name__} in matrix line {self.line} with attributes: {self.__dict__!r}"""

    def tikz(self):
        return ""

    def tikz_arrows(self):
        return ""

    def tikz_markers(self):
        return ''

    def contour(self, text):
        c = getattr(self, 'draw_contour', True)
        if not c:
            return text
        if not text:
            return ''
        return r"\contour{white}{%s}" % text

    @cached_property
    def tikz_extra_style(self):
        if self.style:
            return f",{self.style}"
        return ""

    @cached_property
    def tikz_above(self):
        if not self.text_above and (not getattr(self, 'id_above', True) or not self.tex_id):
            return ""
        else:
            return r"""node [%s,above=2.6pt,anchor=base](%s){%s%s}""" % (
                self.text_style,
                self.create_affecting_node_name(parties=[]),
                self.tex_id if getattr(self, 'id_above', False) else '',
                self.contour(self.text_above)
            )

    @cached_property
    def tikz_below(self):
        if not self.text_below:
            return ""
        else:
            line_counter = 0
            out = ""
            for line in self.lines_below:
                pos = "8pt" + ("+8pt" * line_counter)
                out += r"""node [%s,below=%s,anchor=base](%s){%s} """ % (
                    self.text_style,
                    pos,
                    self.create_affecting_node_name(parties=[]),
                    self.contour(line),
                )
                line_counter += 1
            return out

    def create_affecting_node_name(self, parties=None):
        name = f"{self.annexid}_{self.node_name_counter}"
        self.node_name_counter += 1
        self._affecting_nodes = self._affecting_nodes + [name]

        if parties is None:
            parties = self.affected_parties
        for p in parties:
            p.add_affecting_node(name)
        return name

    def _init(self, protocol, counter, skip_number):
        self.protocol = protocol
        if not self.skip_number and not skip_number:
            self._counter = counter.send(self.counter)

    def formatted_id(self, protocol_option):
        if not self.protocol.options[protocol_option]:
            return ''
        if self.skip_number or not hasattr(self, '_counter'):
            return ''
        if hasattr(self, 'id'):
            t = self.id
        else:
            t = self.annexid
        prefix = self.protocol.options['prefix']
        return self.protocol.options[protocol_option].format(identifier=t, number=(self._counter - 1), prefix=prefix)

    @cached_property
    def tex_id(self):
        return self.formatted_id('enumerate')

    @cached_property
    def html_id(self):
        return self.formatted_id('html_enumerate')

    def set_line(self, line):
        self.line = line
        return 1

    def walk(self):
        yield self

    @property
    def affected_parties(self):
        yield self.party

    @property
    def affecting_nodes(self):
        return list(self._affecting_nodes)

    @property
    def lines_below(self):
        return self.text_below.strip().split("\n")

    def svg_get_x_from_column(self, column):
        return (0.5 + column) * self.protocol.options['aspectratio']
    
        #return int((100.0 / len(self.protocol.columns)) * column)

    def svg_get_y(self, line=None):
        if line is None:
            line = self.line
        return sum(self.protocol.svg_line_maxheights.get(x, 0) for x in range(line))

        
    
class MultiStep(ProtocolStep):
    skip_number = True
    condense = False

    def draw(self):
        for d in self.steps:
            d.draw()

    def _init(self, protocol, counter, skip_number):
        if self.condense or skip_number:
            self.skip_number = False
            skip_numbers = True
        else:
            skip_numbers = False
        super()._init(protocol, counter, skip_number)
        for step in self.steps:
            step._init(protocol, counter, skip_numbers)

    def tikz_markers(self):
        if not self.condense:
            return ""

        if type(self.condense) is not str:
            self.condense = 'north west'

        fit_string = "fit=" + ''.join(f'({x})' for x in self.affecting_nodes)
        gid = self.annexid
        out = fr"""\node[annex_condensed_box,{fit_string}]({gid}) {{}}; """
        out += fr"\node[] at ({gid}.{self.condense}) {{{self.tex_id}}};"
        return out
        
    def walk(self):
        yield self
        for step in self.steps:
            yield from step.walk()

    @property
    def affected_parties(self):
        for step in self.steps:
            yield from step.affected_parties

    @property
    def affecting_nodes(self):
        return chain(*(step.affecting_nodes for step in self.steps))
            

class Parallel(MultiStep):
    yaml_tag = '!Parallel'
    length_fun = max
    html_template = ''
    
    def set_line(self, line):
        length = 0
        for step in self.steps:
            length = max(step.set_line(line), length)
        self.line = line
        self.length = length
        return length
        

class Serial(MultiStep):
    yaml_tag = '!Serial'
    length_fun = sum
    lifeline_style = "annex_lifeline"
    html_template = ''
    
    def set_line(self, line):
        length = 0
        for step in self.steps:
            length += step.set_line(line + length)
        self.line = line
        self.length = length
        return length

    def apply_lifeline_style(self):
        block_start = self.line * 2
        block_end = (self.line + self.length - 1) * 2
        for step in self.protocol.walk():  # TODO: we need to walk over the whole protocol!!!!
            if not hasattr(step, 'lifeline_segments'):
                continue
            for i, segment in zip(range(len(step.lifeline_segments)), step.lifeline_segments):
                segment_start = segment[0]
                segment_end = segment[1]
                if segment_end <= block_start or segment_start >= block_end:
                    continue

                if segment[2] == self.lifeline_style:
                    # segment does not need to be split up
                    continue

                # block affects segment -> split segment
                if block_start > segment_start and block_end >= segment_end:
                    # block affects the end of segment
                    step.lifeline_segments = step.lifeline_segments[:i] + [(segment_start, block_start-1, segment[2]), (block_start-1, segment_end, self.lifeline_style)]
                elif block_start <= segment_start and block_end < segment_end:
                    # block affects start of segment
                    step.lifeline_segments = [(segment_start, block_end + 1, self.lifeline_style), (block_end + 1, segment_end, segment[2])] + step.lifeline_segments[i+1:]
                elif block_start <= segment_start and block_end >= segment_end:
                    # block affects whole segment
                    step.lifeline_segments = [(segment_start, segment_end, self.lifeline_style)]
                elif block_start > segment_start and block_end < segment_end:
                    # block affects middle of segment
                    step.lifeline_segments = step.lifeline_segments[:i] + [(segment_start, block_start - 1, segment[2]), (block_start - 1, block_end + 1, self.lifeline_style), (block_end + 1, segment_end, segment[2])] + step.lifeline_segments[i+1:]


class Protocol(Serial):
    yaml_tag = '!Protocol'
    extra_steps = []
    counter = 0
    columns = []
    html_template = ''

    def init(self, options, unique_id):
        self.options = options
        self.unique_id = unique_id
        # Set line numbers for each step
        self.set_line(1 if self.has_groups else 0)

        # Set column numbers for parties
        self.columns = []
        for p in self.parties:
            if p.column == None:
                p.column = len(self.columns)
                if hasattr(p, 'extrawidth'):
                    self.columns.append({'num': len(self.columns), 'extrawidth': p.extrawidth, 'party': p, 'parties': []})
                else:
                    self.columns.append({'num': len(self.columns), 'parties': []})
        for p in self.parties:
            if isinstance(p.column, Party):
                p.column = p.column.column
            self.columns[p.column]['parties'].append(p)
        

        step_counter = count(start=0, step=1)
        next(step_counter)  # initialize counter, it is now at 1
        self._init(self, step_counter, False)

        # determine start and end points of lifelines
        last_starts = {}
        for step in self.walk():
            if getattr(step, 'dummyparty', False):
                continue
            elif getattr(step, 'startsparty', False):
                if step.party in last_starts:
                    raise Exception("Started party that was already started: " + repr(step.party))
                last_starts[step.party] = step
            elif getattr(step, 'endsparty', False):
                if step.party not in last_starts:
                    raise Exception("Ended party that was not started: " + repr(step.party))
                last_starts[step.party].end = step
                last_starts[step.party].lifeline_segments = [(last_starts[step.party].line * 2, step.line * 2, "annex_lifeline")]
                del last_starts[step.party]
        if len(last_starts):
            raise Exception("Party was started but not ended: " + repr(last_starts))
        # apply lifeline styles
        for step in self.walk():
            if getattr(step, 'lifeline_style', False):
                step.apply_lifeline_style()


    @property
    def has_groups(self):
        return hasattr(self, 'groups') and self.groups is not None


class Party(ProtocolObject):
    yaml_tag = '!Party'
    style = ''
    column = None

    def add_affecting_node(self, node):
        if hasattr(self, '_affecting_nodes'):
            self._affecting_nodes.append(node)
        else:
            self._affecting_nodes = [node]

    @property
    def fit_string(self):
        if hasattr(self, '_affecting_nodes'):
            return self._affecting_nodes
        else:
            return ()


class Group(ProtocolObject):
    yaml_tag = '!Group'
    html_template = """
    <div class="partygroup" style="grid-area: 1 / {{ this.first_party.annexid}} / span {{ protocol.length }} / {{ this.last_party.annexid }}"></div><div class="partygroup_text" style="grid-area: 1 / {{ this.first_party.annexid}} / 1 / {{ this.last_party.annexid }}">{{ this.name }}</div>
    """

    def tikz_desc(self):
        return f"""% drawing group {self.name}"""

    @cached_property
    def first_party(self):
        columns_of_parties = {p.column:p for p in self.parties}
        first_column = min(columns_of_parties)
        return columns_of_parties[first_column]

    @cached_property
    def last_party(self):
        columns_of_parties = {p.column:p for p in self.parties}
        last_column = max(columns_of_parties)
        return columns_of_parties[last_column]        

    def tikz_groups(self, num_lines):
        fit_string = "fit=" + ''.join(f'({x})' for x in chain(
            [self.get_pos(self.first_party.column, 0)],
            self.first_party.fit_string,
            self.last_party.fit_string,
        ))
        gid = self.annexid
        return fr"""\node[annex_group_box,{fit_string}]({gid}) {{}}; \node[anchor=base,above=of {gid}.north,above=-2.5ex,anchor=base] {{{self.name}}};"""

class Separator(ProtocolStep):
    skip_number = True
    html_template = """<div class="separator" style="grid-column-start: start; grid-column-end: end; grid-row-start: {{ this.line + 1}}"></div>"""

    def tikz_arrows(self):
        src = self.get_pos(self.protocol.parties[0].column, self.line)
        dest = self.get_pos(self.protocol.parties[-1].column, self.line)
        out = fr"""%% draw separator line
        \draw[annex_separator{self.tikz_extra_style}] ({src}) to  ({dest});"""
        out += super().tikz_arrows()
        return out

    @property
    def height(self):
        return "2ex", "center"

    @classmethod
    def constructor(cls, loader, node):
        return cls()


class Comment(ProtocolStep):
    yaml_tag = '!comment'
    id_above = False
    skip_number = True
    text_style = 'annex_comment_text'
    html_template = """<div class="comment" style="grid-column-start: start; grid-column-end: end; grid-row-start: {{ this.line + 1}}"><span>{{ this.label }}</span></div>"""

    def tikz_arrows(self):
        src = self.get_pos(self.protocol.parties[0].column, self.line)
        dest = self.get_pos(self.protocol.parties[-1].column, self.line)
        self.text_below = self.label
        out = fr"""%% draw comment
        \draw[draw=none] ({src}) to {self.tikz_below} ({dest});"""
        out += super().tikz_arrows()
        return out
    
    @property
    def height(self):
        return "3ex", "center,yshift=-1ex"
    
    @property
    def affected_parties(self):
        yield from []

        
yaml.add_constructor('!separator', Separator.constructor)
pattern = re.compile(r'^-{3,}$')
yaml.add_implicit_resolver('!separator', pattern)
