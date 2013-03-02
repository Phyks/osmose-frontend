#! /usr/bin/env python
#-*- coding: utf-8 -*-

###########################################################################
##                                                                       ##
## Copyrights Etienne Chové <chove@crans.org> 2009                       ##
##                                                                       ##
## This program is free software: you can redistribute it and/or modify  ##
## it under the terms of the GNU General Public License as published by  ##
## the Free Software Foundation, either version 3 of the License, or     ##
## (at your option) any later version.                                   ##
##                                                                       ##
## This program is distributed in the hope that it will be useful,       ##
## but WITHOUT ANY WARRANTY; without even the implied warranty of        ##
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         ##
## GNU General Public License for more details.                          ##
##                                                                       ##
## You should have received a copy of the GNU General Public License     ##
## along with this program.  If not, see <http://www.gnu.org/licenses/>. ##
##                                                                       ##
###########################################################################

from bottle import route, request, response
from tools import utils
import datetime, re


def _build_where_item(item, table):
    if item == '':
        where = "1=2"
    elif item == None or item == 'xxxx':
        where = "1=1"
    else:
        where = []
        l = []
        for i in item.split(','):
            try:
                if 'xxx' in i:
                    where.append("%s.item/1000 = %s" % (table, int(i[0])))
                else:
                    l.append(str(int(i)))
            except:
                pass
        if l != []:
            where.append("%s.item IN (%s)" % (table, ','.join(l)))
        if where != []:
            where = "(%s)" % ' OR '.join(where)
        else:
            where = "1=1"
    return where


def _build_param(bbox, source, item, level, username, classs, country, active, status, forceTable=[], stats=False):
    join = ""
    where = ["1=1"]

    if stats:
        join += "dynpoi_stats AS marker"
    elif status in ("done", "false"):
        join += "dynpoi_status AS marker"
        where.append("marker.status = '%s'" % status)
    else:
        join += "marker"

    if source:
        sources = source.split(",")
        source2 = []
        for source in sources:
            source = source.split("-")
            if len(source)==1:
                source2.append("(marker.source=%d)"%int(source[0]))
            else:
                source2.append("(marker.source=%d AND marker.class=%d)"%(int(source[0]), int(source[1])))
        sources2 = " OR ".join(source2)
        where.append("(%s)" % sources2)

    tables = list(forceTable)
    tablesLeft = []

    if item:
        tables.append("dynpoi_class")
    if level and level != "1,2,3":
        tables.append("dynpoi_class")
    if country:
        tables.append("dynpoi_source")
    if not status in ("done", "false"):
        if active and active != "all":
            tables.append("dynpoi_item")
        elif not active:
            tableLeft.append("dynpoi_item")
        if username:
            tables.append("marker_elem")

    if "dynpoi_class" in tables or "dynpoi_source" in tables:
        itemField = "dynpoi_class"
    else:
        itemField = "marker"

    if "dynpoi_class" in tables or "dynpoi_source" in tables:
        join += """
        JOIN dynpoi_class ON
            marker.source = dynpoi_class.source AND
            marker.class = dynpoi_class.class"""

    if "dynpoi_source" in tables:
        join += """
        JOIN dynpoi_source ON
            dynpoi_class.source = dynpoi_source.source"""

    if "dynpoi_item" in tables:
        join += """
        JOIN dynpoi_item ON
            %s.item = dynpoi_item.item""" % itemField

    if "marker_elem" in tables:
        join += """
        JOIN marker_elem ON
            marker_elem.marker_id = marker.id"""

    if item:
        where.append(_build_where_item(item, itemField))

    if level != "1,2,3":
        where.append("dynpoi_class.level IN (%s)" % level)

    if classs:
        where.append("marker.class = %d"%int(classs))

    if bbox:
        where.append("marker.lat BETWEEN %s AND %s" % (bbox[1], bbox[3]))
        where.append("marker.lon BETWEEN %s AND %s" % (bbox[0], bbox[2]))

    if country:
        if country[-1] == "*":
            country = country[:-2] + "%"
        where.append("dynpoi_source.comment LIKE '%%%s'" % ("-" + country))

    if not status in ("done", "false") and not active:
        where.append("dynpoi_item.item IS NULL")

    if not status in ("done", "false") and username:
        where.append("marker_elem.username = '%s'" % username)

    return (join, " AND\n        ".join(where))


def _params():
    class Params:
        lat      = int(request.params.get('lat', type=float, default=0)*1000000)
        lon      = int(request.params.get('lon', type=float, default=0)*1000000)
        bbox     = request.params.get('bbox', default=None)
        item     = request.params.get('item')
        source   = request.params.get('source', default='')
        classs   = request.params.get('class', default='')
        username = utils.pg_escape(unicode(request.params.get('username', default='')))
        level    = request.params.get('level', default='1,2,3')
        full     = request.params.get('full', default=False)
        zoom     = request.params.get('zoom', type=int, default=10)
        limit    = request.params.get('limit', type=int, default=100)
        country  = request.params.get('country', default=None)
        active   = request.params.get('active', default=True)
        status   = request.params.get('status', default="open")

    params = Params()

    if params.level:
        params.level = params.level.split(",")
        params.level = ",".join([str(int(x)) for x in params.level if x])
    if params.bbox:
        try:
            params.bbox = map(lambda x: int(float(x) * 1000000), params.bbox.split(','))
            if not params.lat or params.lat==0:
                params.lat = (params.bbox[1] + params.bbox[3]) / 2
            if not params.lon or params.lon==0:
                params.lon = (params.bbox[0] + params.bbox[2]) / 2
        except:
            params.bbox = None
    if params.limit > 500:
        params.limit = 500
    if params.country and not re.match(r"^([a-z_]+)(\*|)$", params.country):
        params.country = None
    if params.active == "false":
        params.active = False

    return params


def _gets(db, params):
    sqlbase = """
    SELECT"""
    if not params.status in ("done", "false"):
        sqlbase += """
        marker.id,
        marker.item,"""
    elif params.full:
        sqlbase += """
        -1 AS id,
        dynpoi_class.item,"""
    else:
        sqlbase += """
        -1 AS id,
        -1 AS item,"""
    sqlbase += """
        marker.lat,
        marker.lon"""
    if params.full:
        sqlbase += """,
        marker.source,
        marker.class,
        marker.elems,
        marker.subclass,
        marker.subtitle,
        dynpoi_source.comment,
        dynpoi_class.title,
        dynpoi_class.level,
        dynpoi_update_last.timestamp"""
        if not params.status in ("done", "false"):
            sqlbase += """,
        dynpoi_item.menu,
        marker_elem.username,
        -1 AS date"""
        else:
            sqlbase += """,
        '' AS menu,
        '' AS username,
        marker.date"""
    sqlbase += """
    FROM
        %s
        JOIN dynpoi_update_last ON
            marker.source = dynpoi_update_last.source
    WHERE
        %s --AND
--        dynpoi_update_last.timestamp > (now() - interval '3 months')
    """
    if params.lat and params.lon:
        sqlbase += """
    ORDER BY
        point(marker.lat, marker.lon) <-> point(%d, %d)""" % (params.lat, params.lon)
    sqlbase += """
    LIMIT
        %s"""

    if params.full:
        if not params.status in ("done", "false"):
            forceTable = ["dynpoi_class", "dynpoi_source", "marker_elem"]
        else:
            forceTable = ["dynpoi_class", "dynpoi_source"]
    else:
        forceTable = []

    join, where = _build_param(params.bbox, params.source, params.item, params.level, params.username, params.classs, params.country, params.active, params.status, forceTable=forceTable)
    sql = sqlbase % (join, where, params.limit)
    db.execute(sql) # FIXME pas de %
    results = db.fetchall()

    return results


def _count(db, params, by, extraFrom=[], extraFields=[], orderBy=False):
    params.full = False
    byTable = set(map(lambda x: x.split('.')[0], by) + extraFrom)
    sqlbase  = """
    SELECT
        %s,
        count(*) AS count
    FROM
        %s
        JOIN dynpoi_update_last ON
            marker.source = dynpoi_update_last.source
    WHERE
        %s
    GROUP BY
        %s
    ORDER BY
        %s
    LIMIT
        %s
    """

    select = ",\n        ".join(by+extraFields)
    groupBy = ",\n        ".join(by)
    if orderBy:
        order = groupBy
    else:
        order = "count DESC"

    join, where = _build_param(params.bbox, params.source, params.item, params.level, params.username, params.classs, params.country, params.active, params.status, forceTable=byTable)
    sql = sqlbase % (select, join, where, groupBy, order, params.limit)
    db.execute(sql) # FIXME pas de %
    results = db.fetchall()

    return results