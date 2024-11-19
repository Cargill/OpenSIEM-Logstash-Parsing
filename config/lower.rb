# Initialize with...
def register(params)
  @ignore = [ "path", "@timestamp", "@metadata", "host", "@version" ]
end

# Create new array
def processArray(a)
  newArray = []
  a.each { |x|
    newArray << processObject(x)
  }
  return newArray
end

# Create new hash with keys/values lowercased
def processHash(h)
  newHash = {}
  h.each { |k, v|
    newHash[k.downcase] = processObject(v)
  }
  return newHash
end

# Check type of object
def processObject(v)
  if v.kind_of?(Array)
    return processArray(v)
  elsif v.kind_of?(Hash)
    return processHash(v)
  else
    return v
  end
end

# Main func called by logstash
def filter(event)
  event.to_hash.each { |k, v|
    unless @ignore.include?(k)
      event.remove(k)
      event.set(k.downcase, processObject(v))
    end
  }
  return [event]
end